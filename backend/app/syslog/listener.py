"""Syslog network transports: UDP, TCP (TLS hooks in for a later phase)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from app.core.config import get_settings
from app.syslog.framing import TcpFrameDecoder

logger = logging.getLogger(__name__)

# Callback signature shared by every transport: (raw_bytes, source_ip)
MessageHandler = Callable[[bytes, str], None]

settings = get_settings()


class BaseSyslogTransport:
    """Interface every transport (UDP/TCP/TLS) implements."""

    name: str = "base"

    def __init__(self, host: str, port: int, on_message: MessageHandler) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
        self.running = False
        self.messages_received = 0
        self.last_message_at: datetime | None = None

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def _record_message(self) -> None:
        self.messages_received += 1
        self.last_message_at = datetime.now(timezone.utc)

    def stats(self) -> dict:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "running": self.running,
            "messages_received": self.messages_received,
            "last_message_at": self.last_message_at.isoformat()
            if self.last_message_at
            else None,
        }


class _UdpSyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self, transport_owner: "UdpSyslogTransport") -> None:
        self._owner = transport_owner

    def datagram_received(self, data: bytes, addr) -> None:
        self._owner._record_message()
        self._owner.on_message(data, addr[0])


class UdpSyslogTransport(BaseSyslogTransport):
    """Plain UDP syslog listener (RFC 3164/5424 over datagrams)."""

    name = "udp"

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        udp_transport, _ = await loop.create_datagram_endpoint(
            lambda: _UdpSyslogProtocol(self),
            local_addr=(self.host, self.port),
        )
        self._transport = udp_transport
        self.running = True
        logger.info("Syslog UDP listener bound on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        self.running = False
        transport = getattr(self, "_transport", None)
        if transport is not None:
            transport.close()
        logger.info("Syslog UDP listener stopped on %s:%s", self.host, self.port)


class TcpSyslogTransport(BaseSyslogTransport):
    """Plain TCP syslog listener with RFC 6587 framing support."""

    name = "tcp"

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self.running = True
        logger.info("Syslog TCP listener bound on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        self.running = False
        server = getattr(self, "_server", None)
        if server is not None:
            server.close()
            await server.wait_closed()
        logger.info("Syslog TCP listener stopped on %s:%s", self.host, self.port)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        source_ip = peer[0] if isinstance(peer, tuple) else str(peer)
        decoder = TcpFrameDecoder(max_bytes=settings.syslog_max_message_bytes)
        try:
            while True:
                chunk = await reader.read(8192)
                if not chunk:
                    break
                for frame in decoder.feed(chunk):
                    self._record_message()
                    self.on_message(frame, source_ip)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TCP client handler failed for %s", source_ip)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # pragma: no cover - client vanished mid-close
                pass


class SyslogListenerManager:
    """Owns the transport lifecycle and aggregates listener statistics.

    Adding TLS (port 6514) later only requires appending another transport
    factory to :meth:`_transport_factories`.
    """

    def __init__(self, on_message: MessageHandler) -> None:
        self._on_message = on_message
        self._transports: list[BaseSyslogTransport] = []
        self.errors: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return settings.syslog_listeners_enabled

    @property
    def running(self) -> bool:
        return any(transport.running for transport in self._transports)

    def _transport_factories(
        self,
    ) -> list[tuple[str, Callable[[], BaseSyslogTransport]]]:
        factories: list[tuple[str, Callable[[], BaseSyslogTransport]]] = [
            (
                "udp",
                lambda: UdpSyslogTransport(
                    settings.syslog_udp_host,
                    settings.syslog_udp_port,
                    self._on_message,
                ),
            ),
            (
                "tcp",
                lambda: TcpSyslogTransport(
                    settings.syslog_tcp_host,
                    settings.syslog_tcp_port,
                    self._on_message,
                ),
            ),
        ]
        # TLS transport (RFC 5425 style, default port 6514) is registered here
        # in a later phase — kept off until the transport implementation exists.
        if settings.syslog_tls_enabled:
            logger.warning(
                "SYSLOG_TLS_ENABLED=true but the TLS transport is not implemented "
                "yet (planned for a later phase) — skipping TLS listener"
            )
        return factories

    async def start_all(self) -> None:
        for name, factory in self._transport_factories():
            transport = factory()
            try:
                await transport.start()
                self._transports.append(transport)
            except Exception as exc:
                self.errors[name] = f"{exc.__class__.__name__}: {exc}"
                logger.exception("Failed to start syslog %s listener", name)

    async def stop_all(self) -> None:
        for transport in self._transports:
            try:
                await transport.stop()
            except Exception:  # pragma: no cover - shutdown best effort
                logger.exception("Error stopping syslog %s listener", transport.name)
        self._transports = []

    def stats(self) -> dict:
        if not self.enabled:
            status = "disabled"
        elif self.running and not self.errors:
            status = "ok"
        elif self.running:
            status = "degraded"
        elif self.errors:
            status = "error"
        else:
            status = "stopped"
        return {
            "status": status,
            "transports": [transport.stats() for transport in self._transports],
            "errors": dict(self.errors),
        }
