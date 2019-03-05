import paramiko
from .utilities import TS3Exception
from os.path import isfile


class SSHConnWrapper(object):
    def __init__(self, host, port, username, password, accept_all_keys=False, host_key_file=None, use_system_hosts=False):
        self._buffer = b""
        self._ssh_conn = paramiko.SSHClient()
        if accept_all_keys:
            self._ssh_conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            self._ssh_conn.set_missing_host_key_policy(paramiko.RejectPolicy())
        if use_system_hosts:
            self._ssh_conn.load_system_host_keys()
        if host_key_file is not None and isfile(host_key_file):
            self._ssh_conn.load_host_keys(host_key_file)
        if username is not None and password is not None:
            self._ssh_conn.connect(host, port=port, username=username, password=password)
            if host_key_file is not None:
                self._ssh_conn.save_host_keys(host_key_file)
            self._channel = self._ssh_conn.invoke_shell("raw")
        else:
            raise TS3Exception("Connecting via ssh requires a password.")

    def read_until(self, delimiter):
        while True:
            delimiter_pos = self._buffer.find(delimiter)
            if delimiter_pos == -1:
                self._buffer += self._channel.recv(4096)
            else:
                break
        data = self._buffer[:delimiter_pos+len(delimiter)]
        self._buffer = self._buffer[delimiter_pos+len(delimiter):]
        return data

    def write(self, data):
        self._channel.send(data)
