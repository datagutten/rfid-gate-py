import logging

import flask
from flask import Flask, jsonify

from feig.gate_socket import FeigGate

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(
    filename='/var/log/gate/gate_api.log',
    level=logging.DEBUG,
    filemode="a",
    format="{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M",
)
connections = {}


@app.errorhandler(RuntimeError)
def handle_exception(error):
    logger.error('RuntimeError: %s', error)
    response = jsonify({'error': str(error)})
    response.status_code = 500
    return response


@app.errorhandler(TimeoutError)
def handle_timeout_exception(error):
    logger.error('Timeout: %s', error)
    response = jsonify({'error': 'Timeout'})
    response.status_code = 500
    return response


@app.errorhandler(ConnectionError)
def hande_connection_error(error):
    logger.error('Connection error: %s', error)
    for ip, conn in connections.items():
        try:
            conn.close()
            del connections[ip]
            get_connection(ip)
        except OSError as e:
            del connections[ip]


def get_connection(gate_id=None):
    if gate_id is None:
        gate_id = flask.request.args.get('gate')
    if gate_id not in connections:
        try:
            logger.info('Connect to %s', gate_id)
            gate_obj = FeigGate(gate_id)
            connections[gate_id] = gate_obj
        except ConnectionError as e:
            raise RuntimeError from e
    else:
        gate_obj = connections[gate_id]

    gate_obj.save = True

    return gate_obj


@app.route('/')
def hello():
    return 'Hello, World!'


@app.route('/people')
def count():
    gate_obj = get_connection(flask.request.args.get('gate'))
    counter = gate_obj.people_count()
    return {'in': counter.people_in, 'out': counter.people_out, 'raw': counter.base64()}


@app.route('/info')
def info():
    gate_obj = get_connection()
    info_obj = gate_obj.gate_info
    return {
        'hardware_type': info_obj.hardware_type,
        'serial': info_obj.id,
        'ip': info_obj.ip,
        'netmask': info_obj.netmask,
        'gateway': info_obj.gateway,
        'mac': info_obj.mac,
        'peripheral_count': info_obj.peripheral_count,
        'reader_type': info_obj.reader_type,
        'rx_buffer': info_obj.rx_buffer,
        'tx_buffer': info_obj.tx_buffer,
        'status': info_obj.status,
        'transponder_types': info_obj.transponder_types,
        'version': info_obj.version,
        'raw': info_obj.base64(),
    }


@app.route('/buffer')
def buffer():
    gate_obj = get_connection()
    buffer_data = gate_obj.read_buffer()

    data = {
        'raw': buffer_data.base64(),
        'status': buffer_data.status,
        'tags': [],
    }

    try:
        data['tags'] = buffer_data.dict()
    except RuntimeError as e:
        logger.error('Error reading buffer: %s', str(e))
        data['error'] = str(e)

    return data


@app.route('/buffer_clear')
def buffer_clear():
    gate_obj = get_connection()
    response = gate_obj.clear_buffer()
    return {'raw': response.base64(), 'success': response.success}


@app.route('/raw', methods=["POST"])
def raw():
    gate_obj = get_connection()
    data = flask.request.data
    response = gate_obj.send_read(data)
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0')
