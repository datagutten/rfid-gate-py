import logging
import os
import socket
import time
from pathlib import Path

from feig import FeigRequest
from feig import response as feig_response

logger = logging.getLogger(__name__)


class FeigGate:
    ip: str
    port: int
    socket: socket.socket
    gate_id: int = 0
    gate_info = feig_response.ReaderInfoResponse
    save: bool = False
    detectors: int = 1
    connected: bool = False

    def __init__(self, ip: str, port: int = 10001, save=True):
        self.ip = ip
        self.port = port
        self.save = save

        if self.save:
            self.data_folder = Path(os.getenv('DATA_FOLDER', 'data'), str(self.gate_id))
            if not self.data_folder.exists():
                self.data_folder.mkdir(parents=True)

    def __str__(self):
        if self.gate_id:
            return 'IP %s serial %d' % (self.ip, self.gate_id)
        else:
            return 'IP %s' % self.ip

    def __del__(self):
        self.socket.close()

    def connect(self):
        logger.info('Connecting to %s:%d' % (self.ip, self.port))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(1)
        self.socket.connect((self.ip, self.port))

        self.gate_info = self.info()
        self.gate_id = self.gate_info.id
        logger.info('Connected to gate %s' % self)
        self.connected = True

    def close(self):
        logger.info('Closing socket to gate %s' % self.gate_id)
        self.connected = False
        self.socket.close()

    def send_read(self, data, save=True):
        timestamp = int(time.time())
        self.socket.sendall(data)
        response = self.socket.recv(1024)
        if save:
            self.data_folder.joinpath('request_%s.txt' % timestamp).write_bytes(data)
            self.data_folder.joinpath('response_%s.txt' % timestamp).write_bytes(response)

        return response

    def request(self, data: bytes, command: int = None, save=True):
        request_obj = FeigRequest.parse_request(data)
        logger.debug('Request command %d to gate %d IP %s', command or request_obj.command, self.gate_id, self.ip)
        response = self.send_read(data, save)
        return feig_response.FeigResponse.parse_response(response, command, request_obj)

    def system_time(self):
        query = b'\x02\x00\x07\xFF\x88\x85\x5D'

    def info(self) -> feig_response.ReaderInfoResponse:
        logger.info('Get gate info')
        query = b'\x02\x00\x08\xFF\x66\xFF\xF0\x1D'
        return self.request(query, command=0x66, save=False)

    def people_count(self) -> feig_response.PeopleCounterResponse:
        query = b'\x02\x00\x12\xFF\x9F\x00\x0D\x02\x02\x00\x08\x01\x77\x00\xEE\x02\x44\x31'
        return self.request(query, save=False)

    def read_buffer(self) -> feig_response.ReadBuffer:
        query = b'\x02\x00\x09\xFF\x22\x00\xFF\x79\x69'
        return self.request(query)

    def clear_buffer(self):
        query = b'\x02\x00\x07\xFF\x32\x54\x47'
        return self.request(query, save=False)
