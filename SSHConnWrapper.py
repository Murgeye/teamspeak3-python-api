import paramiko
from .utilities import TS3Exception, TS3ConnectionClosedException
from os.path import isfile
import socket


class SSHConnWrapper(object):
    def __init__(self, host, port, username, password, accept_all_keys=False, host_key_file=None, use_system_hosts=False, timeout=10, timeout_limit=3):
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
            self._channel.settimeout(timeout)
            self.timeout_limit = timeout_limit
        else:
            raise TS3Exception("Connecting via ssh requires a password.")

    def read_until(self, delimiter):
        timeout_cnt = 0
        while True:
            delimiter_pos = self._buffer.find(delimiter)
            if delimiter_pos == -1:
                try:
                    received = self._channel.recv(4096)
                    timeout_cnt = 0
                except socket.timeout:
                    timeout_cnt += 1
                    if timeout_cnt >= self.timeout_limit:
                        raise TS3ConnectionClosedException("SSH connection timeout limit received!")
                    else:
                        continue
                if len(received) == 0:
                    raise TS3ConnectionClosedException("SSH connection was closed!")
                self._buffer += received
            else:
                break
        data = self._buffer[:delimiter_pos+len(delimiter)]
        self._buffer = self._buffer[delimiter_pos+len(delimiter):]
        return data

    def write(self, data):
        try:
            self._channel.send(data)
        except OSError:
            raise TS3ConnectionClosedException(OSError)

    def close(self):
        self._ssh_conn.close()
