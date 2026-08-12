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
    format="{asctime} - {levelname}\t{name}\t{message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)
connections = {}


@app.errorhandler(RuntimeError)
def handle_exception(error):
    logger.error('RuntimeError: %s', error)
    response = jsonify({'error': str(error)})
    response.status_code = 500
    return response


def handle_os_error(error: OSError, gate_obj: FeigGate = None):
    if not gate_obj:
        logger.error('%s: %s', type(error).__name__, error)
    else:
        logger.error('%s: %s %s', type(error).__name__, error, gate_obj)
        gate_obj.close()
        try:
            gate_obj.connect()
            logger.info('Reconnect succeeded to %s' % gate_obj)
        except OSError as e:
            logger.error('%s reopening connection to %s: %s', type(e).__name__, gate_obj, e)

    response = jsonify({'error': str(error)})
    response.status_code = 500
    return response


def get_connection(gate_ip: str = None):
    if gate_ip is None:
        gate_ip = flask.request.args.get('gate')
    if gate_ip not in connections:
        gate_obj = FeigGate(gate_ip)
        try:
            gate_obj.connect()
            connections[gate_ip] = gate_obj
        except OSError as e:
            handle_os_error(e, gate_obj)
    else:
        gate_obj = connections[gate_ip]

    gate_obj.save = True

    return gate_obj


@app.route('/')
def hello():
    return 'Hello, World!'


@app.route('/people')
def count():
    gate_obj = get_connection()
    try:
        counter = gate_obj.people_count()
    except OSError as e:
        return handle_os_error(e, gate_obj)

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
    try:
        buffer_data = gate_obj.read_buffer()
    except OSError as e:
        return handle_os_error(e, gate_obj)

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
    try:
        response = gate_obj.clear_buffer()
    except OSError as e:
        return handle_os_error(e, gate_obj)
    return {'raw': response.base64(), 'success': response.success}


@app.route('/raw', methods=["POST"])
def raw():
    gate_obj = get_connection()
    data = flask.request.data
    try:
        response = gate_obj.send_read(data)
    except OSError as e:
        return handle_os_error(e, gate_obj)
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0')
