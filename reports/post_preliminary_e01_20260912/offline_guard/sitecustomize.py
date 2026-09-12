"""Guard kiểm H02, tự nạp cả trong Python subprocess; không chặn loopback DB."""
import ipaddress
import json
import os
import sys
from pathlib import Path


class OfflineDispatchBlocked(BaseException):
    """Không cho pipeline catch Exception rồi che mất lần thử egress trái phép."""


def audit(event, args):
    if event not in ('socket.connect', 'socket.getaddrinfo'):
        return
    address = args[1] if event == 'socket.connect' else args[0]
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return
    if host.casefold() in ('localhost', 'localhost.localdomain'):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    path = os.environ.get('H02_DISPATCH_AUDIT')
    if path:
        with Path(path).open('a', encoding='utf-8') as output:
            output.write(json.dumps({'event':event,'host':host,'blocked':True,'pid':os.getpid()})+'\n')
    raise OfflineDispatchBlocked('H02 OFFLINE: chặn external network dispatch')


if os.environ.get('H02_OFFLINE_GUARD') == '1':
    sys.addaudithook(audit)
