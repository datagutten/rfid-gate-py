import datetime
import os.path
import socket
import sys
import time

from feig.gate_socket import FeigGate
from feig.request import parse_header as parse_request_header
from feig.response import parse_header as parse_response_header


class GateProxy:
    connections = {}

    def __init__(self, gate_ip: str):
        print('Starting proxy for %s' % gate_ip)
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.bind(('0.0.0.0', int(os.getenv('PROXY_PORT', 10001))))
        self.listen_socket.listen(1)

        self.listen_conn, addr = self.listen_socket.accept()
        print('Connection from', addr)
        # print('Listening on %s %d', self.listen_socket.ad)
        self.gate = FeigGate(gate_ip)
        self.gate.connect()

    def __del__(self):
        self.listen_conn.close()
        self.listen_socket.close()

    def _request(self, data, save):
        return self.gate.send_read(data, save)

    def listen(self):
        while True:
            data = self.listen_conn.recv(1024)
            if not data:
                continue
            save = True
            command, length, payload, data_format = parse_request_header(data)

            if command == 0x22:
                save = False

            print('%s: Received %d bytes' % (datetime.datetime.now().isoformat(), len(data)))
            try:
                response = self._request(data, save)
            except TimeoutError as e:
                print(e)
                continue
            if command == 0x22:
                try:
                    command, length, payload, data_format = parse_response_header(response)
                    if length > 9:
                        self.gate.data_folder.joinpath('buffer_%s.txt' % int(time.time())).write_bytes(response)
                    pass
                except Exception:
                    pass

            self.listen_conn.send(response)


if __name__ == '__main__':
    proxy = GateProxy(sys.argv[1])
    proxy.listen()
