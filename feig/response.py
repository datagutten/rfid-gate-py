import base64
import re
import struct
import warnings
from typing import Optional

from feig import utils
from feig.utils import format_ip


def parse_header(response: bytes):
    length2 = struct.unpack('>h', response[1:3])
    length2 = int(length2[0])
    length4 = response[0]

    if length4 < len(response):  # Advanced
        length = length2
        data_format = 'isostart'
        command = response[4]
        payload = response[5:]
    else:  # Simple
        length = length4
        data_format = 'rfidif'
        command = response[2]
        payload = response[3:]

    return command, length, payload, data_format


class FeigResponse:
    def __init__(self, response: bytes, request: 'FeigRequest' = None):
        # https://github.com/Amarok79/InlayTester.Drivers.FeigReader/blob/main/src/InlayTester.Drivers.FeigReader/Drivers.Feig/FeigResponse.cs
        if response == b'':
            raise RuntimeError('Empty response')
        self.data = response
        self.request = request
        self.command, self.length, self.payload, self.format = parse_header(response)
        if self.format == 'rfidif':
            if len(self.data) < 6:
                raise RuntimeError('More data needed')
            self.address = self.data[1]
            self.status = self.data[3]
            self.payload2 = self.data[4:self.length - 6]
        else:
            if len(self.data) < 8:
                raise RuntimeError('More data needed')
            self.address = self.data[3]
            self.status = self.data[5]
            self.payload2 = self.data[6:self.length - 8]

        self.success = self.status == 0
        crc_low = self.data[self.length - 2]
        crc_high = self.data[self.length - 1]

        self.crc = (crc_high << 8) | crc_low

        if self.length != len(response):
            warnings.warn('Response length is %d, expected %d' % (len(response), self.length))

    def base64(self):
        return base64.b64encode(self.data).decode()

    def get_field(self, key: bytes | int, length: int, offset=1):
        # if hasattr(self, 'mode') and self.mode != key:
        #     return None

        pos = self.payload.find(key)
        if pos == -1:
            return None
        if type(key) is bytes:
            pos += len(key)
        else:
            pos += 1
        data = self.payload[pos + offset:pos + length + offset]
        return data

    @staticmethod
    def parse_response(response: bytes, command: int = None, request: 'FeigRequest' = None):
        if not command:
            command, length, payload, data_format = parse_header(response)

        if command not in response_classes:
            return FeigResponse(response, request)
        else:
            return response_classes[command](response, request)

    def dict(self) -> Optional[dict]:
        """
        Get object data as dict
        """
        raise NotImplementedError


class PeopleCounterResponse(FeigResponse):
    people_in: int
    people_out: int

    def __init__(self, response: bytes, request=None):
        super().__init__(response, request)

        if not self.request:
            if self.format == 'isostart':
                self.mode = self.payload[5]
            elif self.format == 'rfidif':
                self.mode = self.payload[3]
            else:
                raise RuntimeError('Unknown format %s, unable to get mode' % self.format)

        else:
            self.mode = self.request.mode

        if self.mode == 0x77:
            data_counters = self.get_field(0x77, 8, 1)
            if data_counters:
                self.people_in, self.people_out = struct.unpack('>ii', data_counters)

    def dict(self):
        if not hasattr(self, 'people_in'):
            return None
        return {'in': self.people_in, 'out': self.people_out}


class ReaderInfoResponse(FeigResponse):
    mode: int

    def __init__(self, response: bytes, request):
        data = response
        super().__init__(response, request)
        if self.length < 20 and self.request is None:
            raise RuntimeError('Request is required for partial info requests')
        elif self.request:
            self.mode = self.request.mode
        else:
            self.mode = 0xff  # All info

        # fpga =
        version_data = self.get_field(0x00, 11, 0)
        if version_data:
            data = struct.unpack('>bbbbbbbhh', version_data)
            self.version = data[0:3]
            self.hardware_type = data[3]
            self.reader_type = data[4]
            self.transponder_types = data[5:6]
            self.rx_buffer = data[7]
            self.tx_buffer = data[8]
        peripheral_data = self.get_field(0x61, 5, 0)
        if peripheral_data:
            data = struct.unpack('>bbbbb', peripheral_data)
            self.peripheral_count = data[0]

        id_raw = self.get_field(b'\x00\x00\x80', 4, 0)
        if id_raw:
            self.id = int.from_bytes(id_raw)

        mac = self.get_field(0x50, 6)
        if mac:
            self.mac = utils.hex_string(mac, ':')
        else:
            self.mac = None
        self.ip = format_ip(self.get_field(0x51, 4))
        self.netmask = format_ip(self.get_field(0x52, 4))
        self.gateway = format_ip(self.get_field(0x53, 4))

    def get_field(self, key: bytes | int, length: int, offset=1):
        if self.mode != 0xff and key != self.mode:
            return None
        if self.mode != 0xff:
            key = 0x00

        return super().get_field(key, length, offset)

    def dict(self):
        return {
            # 'mac': utils.hex_string(self.mac).replace(' ', ':'),
            'mac': self.mac,
            'ip': self.ip,
            'netmask': self.netmask,
            'gateway': self.gateway,
        }


class ReadBuffer(FeigResponse):
    valid: bool = True

    def __init__(self, response: bytes, request):
        super().__init__(response, request)
        self.payload = self.payload2
        if self.status == 0x92:
            self.valid = False
            return
        self.requested_sets, self.received_sets = struct.unpack('BxB', self.payload[0:3])
        if self.requested_sets > self.received_sets:
            warnings.warn('Requested sets %s exceeds received sets %d' % (self.requested_sets, self.received_sets))

    def tags(self, num_blocks: int = 4) -> Optional[list[bytes]]:
        """
        Get RFID tags block data
        :return: List of byte strings with tag data
        """
        if not self.valid:
            return None
        tag_start = self.payload.find(b'\xe0')
        if tag_start and self.received_sets == 0:
            self.received_sets = 99

        tags = []
        uids = []
        while len(tags) < self.received_sets:
            try:
                uid, unknown1, num_blocks, block_size = struct.unpack('8scBB', self.payload[tag_start:tag_start + 11])
            except struct.error as e:
                # raise RuntimeError from e
                break

            if uid[0] != 0xe0:  # https://en.wikipedia.org/wiki/ISO/IEC_15693#Implementations
                raise RuntimeError('The first byte of the UID is not 0xE0')
            if block_size not in range(0x01, 0x20):  # Size of a single memory block, valid range = 01...20 (hex)
                raise RuntimeError('Invalid block size')
            uids.append(uid)

            block_start = tag_start + 11
            blocks_raw = self.payload[block_start:block_start + (block_size * num_blocks)]

            blocks = b''

            for pos in range(0, len(blocks_raw), block_size):
                block_data = blocks_raw[pos:pos + block_size]
                blocks += block_data[::-1]  # Reverse bytes in block
            tags.append(blocks)
            tag_end = tag_start + (block_size * num_blocks)
            tag_start = self.payload.find(b'\xe0', tag_end)  # Tag starts with uid
            if not tag_start:
                break

        return tags

    @staticmethod
    def strip_tag(data: bytes) -> str:
        """
        Strip tags for invalid characters at start and end
        :param data: Tag data
        :return: Tag data stripped for invalid characters
        """
        output = ''
        sequences = []
        for byte in data:
            if byte < 32 or byte > 126:
                if output == '':
                    continue  # Skip invalid characters at start
                else:
                    sequences.append(output)
                    output = ''
                    # break  # Stop after first invalid character on output
            else:
                output += chr(byte)
        sequences.append(output)
        longest = 0
        longest_sequence = ''
        for sequence in sequences:
            if re.match(r'.*NO\d{7}$', sequence):  # A short sequence that comes before or after the real tag
                continue
            if len(sequence) > longest:
                longest = len(sequence)
                longest_sequence = sequence
        return longest_sequence

    def dict(self):
        if not self.valid:
            return None
        return list(map(self.strip_tag, self.tags()))


class ReaderDiagnostic(FeigResponse):
    pass


class ReadDataBufferInfo(FeigResponse):
    pass


class GetSoftwareVersion(FeigResponse):
    pass


response_classes = {
    0x22: ReadBuffer,
    0x31: ReadDataBufferInfo,
    0x65: GetSoftwareVersion,
    0x66: ReaderInfoResponse,
    0x6e: ReaderDiagnostic,
    0x9f: PeopleCounterResponse
}
