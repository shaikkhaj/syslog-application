"""Sample syslog generator — emulates Cisco, FortiGate, Juniper and Linux
devices so Phase 1 can be tested without physical hardware.

Examples:
    python tools/syslog_generator.py --host 127.0.0.1 --transport udp --count 20
    python tools/syslog_generator.py --host 127.0.0.1 --transport tcp --scenario cisco
    python tools/syslog_generator.py --host 127.0.0.1 --port 514 --interval 0.2
"""

from __future__ import annotations

import argparse
import random
import socket
import time
from datetime import datetime, timezone

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _bsd_timestamp(now: datetime) -> str:
    return f"{MONTHS[now.month - 1]:>3} {now.day:2d} {now:%H:%M:%S}"


def _iso_timestamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _fortigate_timestamp(now: datetime) -> str:
    return now.strftime("date=%Y-%m-%d time=%H:%M:%S")


def cisco_messages(now: datetime) -> list[str]:
    ts = _bsd_timestamp(now)
    return [
        f"<134>{ts} rtr-core-01: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down",
        f"<134>{ts} rtr-core-01: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to up",
        f"<134>{ts} rtr-core-01: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet0/1, changed state to down",
        f"<130>{ts} rtr-core-01: %SYS-5-CONFIG_I: Configured from console by admin on vty0 (10.0.0.5)",
        f"<131>{ts} sw-access-01: %SEC_LOGIN-5-LOGIN_FAILED: Login failed [user: root] [Source: 10.0.0.99] at 10:23:45 UTC",
        f"<135>{ts} rtr-core-01: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 Down - Connection closed by remote host",
        f"<134>{ts} rtr-core-01: %BGP-5-ADJCHANGE: neighbor 10.10.10.1 Up - Opened",
        f"<134>{ts} rtr-core-01: %OSPF-5-ADJCHG: Nbr 10.10.10.2 on GigabitEthernet0/0 from FULL to DOWN, Neighbor Down",
        f"<133>{ts} sw-access-01: %CPU_FALLBACK-3-HIGH_CPU: cpu_utilization=95% threshold=80% interval=60s",
        f"<132>{ts} sw-access-01: %SYS-3-MEMHIGH: memory_usage=94% threshold=90% high memory utilization",
        f"<134>{ts} rtr-core-01: %IPRT-5-ROUTE_CHANGE: route 10.9.0.0/16 changed via 10.10.10.2",
        f"<130>{ts} rtr-core-01: %IPRT-4-UNREACHABLE: No route to host 10.5.5.5",
    ]


def fortigate_messages(now: datetime) -> list[str]:
    ts = _fortigate_timestamp(now)
    return [
        f'<185>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0000000013" '
        f'type="traffic" subtype="forward" level="warning" srcip=10.10.5.50 srcport=51234 '
        f'dstip=93.184.216.34 dstport=443 proto=6 action="deny" policyid=0 '
        f'msg="denied by forward-policy default"',
        f'<187>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020001" '
        f'type="admin" subtype="login" level="notice" srcip=10.10.5.10 action="login" '
        f'user="admin" msg="Administrator admin logged in successfully from Web GUI"',
        f'<186>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020007" '
        f'type="event" subtype="interface" level="error" interface="port1" '
        f'msg="Interface port1 is down"',
        f'<186>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020007" '
        f'type="event" subtype="interface" level="information" interface="port1" '
        f'msg="Interface port1 is up"',
        f'<184>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020009" '
        f'type="system" subtype="memory" level="error" msg="memory_usage=92% '
        f'threshold=90% high memory utilization"',
        f'<184>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020010" '
        f'type="system" subtype="cpu-usage" level="warning" msg="cpu_usage=96% '
        f'threshold=90% high cpu"',
        f'<187>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020002" '
        f'type="admin" subtype="login" level="warning" srcip=203.0.113.44 '
        f'action="login-failed" user="admin" msg="Administrator login failed from Web GUI"',
        f'<186>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020011" '
        f'type="event" subtype="global-setting" level="information" user="admin" '
        f'msg="Configuration is changed by administrator"',
        f'<186>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100030001" '
        f'type="event" subtype="router" level="notice" msg="static route '
        f'10.20.0.0/24 changed via 10.10.5.1"',
        f'<186>{ts} devname="FGT60F-001" devid="FG60F000000001" logid="0100020004" '
        f'type="event" subtype="ipsec" level="error" tunnel="FGT-to-DC" '
        f'msg="IPSec tunnel is down"',
    ]


def juniper_messages(now: datetime) -> list[str]:
    ts = _bsd_timestamp(now)
    return [
        f"<14>{ts} mx-edge-01 rpd[1234]: BGP - 10.10.20.1 External AS 65002 keepalive "
        f"error: Connection closed by remote host",
        f"<14>{ts} mx-edge-01 rpd[1234]: BGP - 10.10.20.1 External AS 65002 state moved "
        f"from OpenConfirm to Established",
        f"<14>{ts} mx-edge-01 rpd[1234]: OSPF neighbor 10.10.20.2 (via ge-0/0/0) state "
        f"moved from Full to Down",
        f"<14>{ts} mx-edge-01 rpd[1234]: OSPF neighbor 10.10.20.2 (via ge-0/0/0) state "
        f"moved from Down to Full",
        f'<14>{ts} mx-edge-01 mgd[2222]: UI_COMMIT_COMPLETED: cli command "commit" '
        f"executed by operator",
        f"<14>{ts} mx-edge-01 kernel: ge-0/0/0: link down, flapping detected",
        f"<12>{ts} mx-edge-01 bfdd[1337]: BFD session 10.10.20.1 state changed to Down",
        f"<14>{ts} mx-edge-01 rpd[1234]: RTM_NEW: 172.16.10.0/24 via 10.10.20.1 "
        f"flags RTF_GATEWAY",
        f"<14>{ts} mx-edge-01 rpd[1234]: RTM_DEL: 172.16.11.0/24 via 10.10.20.1",
    ]


def linux_messages(now: datetime) -> list[str]:
    ts = _bsd_timestamp(now)
    iso = _iso_timestamp(now)
    return [
        f"<85>1 {iso} web01 sshd - - - Failed password for invalid user admin from "
        f"203.0.113.10 port 54321 ssh2",
        f"<85>1 {iso} web01 sshd - - - Failed password for root from 203.0.113.10 port "
        f"54322 ssh2",
        f"<30>1 {iso} db01 kernel - - - eth1: NIC Link is Down",
        f"<30>1 {iso} db01 kernel - - - eth1: NIC Link is Up 1000 Mbps full duplex",
        f"<14>{ts} web01 systemd[1]: Started nginx.service - A high performance web server",
        f"<14>{ts} web01 hostagent: cpu_utilization=93% threshold=80% memory_usage=91% "
        f"threshold=90% high cpu",
        f"<110>{ts} web01 sudo: pam_unix(sudo:session): session opened for user root by "
        f"deploy(uid=1000)",
        f"<14>{ts} db01 kernel: [12345.678] eth1: interface error: input errors 120, "
        f"CRC errors 3",
        f"<14>{ts} web01 hostagent: configuration file /etc/nginx/nginx.conf changed "
        f"by user deploy",
        f"<14>{iso} web01 networkd[500]: eth0: route added: 10.10.30.0/24 via 192.168.1.1",
        f"<11>{ts} web01 probe[888]: probe failed: connect to 10.9.9.9:443 - "
        f"No route to host",
    ]


SCENARIOS = {
    "cisco": cisco_messages,
    "fortigate": fortigate_messages,
    "juniper": juniper_messages,
    "linux": linux_messages,
}


def build_messages(scenario: str, now: datetime) -> list[str]:
    if scenario == "all":
        messages: list[str] = []
        for builder in SCENARIOS.values():
            messages.extend(builder(now))
        return messages
    return SCENARIOS[scenario](now)


def send_udp(host: str, port: int, payload: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, (host, port))


def send_tcp(host: str, port: int, payload: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect((host, port))
        # Non-transparent (newline) framing — accepted by the TCP decoder.
        sock.sendall(payload + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send sample syslog messages")
    parser.add_argument("--host", default="127.0.0.1", help="collector host")
    parser.add_argument("--port", type=int, default=514, help="collector port")
    parser.add_argument("--transport", choices=["udp", "tcp"], default="udp")
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="all",
        help="which vendor's messages to send",
    )
    parser.add_argument("--count", type=int, default=20, help="messages to send")
    parser.add_argument(
        "--interval", type=float, default=0.25, help="seconds between sends"
    )
    args = parser.parse_args()

    sender = send_udp if args.transport == "udp" else send_tcp
    sent = 0
    print(
        f"Sending {args.count} syslog messages ({args.scenario}) "
        f"to {args.host}:{args.port}/{args.transport.upper()} ..."
    )
    for index in range(args.count):
        now = datetime.now(timezone.utc)
        message = random.choice(build_messages(args.scenario, now))
        try:
            sender(args.host, args.port, message.encode("utf-8"))
            sent += 1
            print(f"[{index + 1:>3}/{args.count}] {message[:110]}")
        except OSError as exc:
            print(f"[{index + 1:>3}/{args.count}] FAILED: {exc}")
            break
        time.sleep(args.interval)
    print(f"Done - {sent}/{args.count} messages sent.")


if __name__ == "__main__":
    main()
