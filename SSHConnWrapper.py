import socket
from os.path import isfile

import paramiko

from .utilities import TS3Exception, TS3ConnectionClosedException


class SSHConnWrapper:
    def __init__(self, host, port, username, password, accept_all_keys=False, host_key_file=None,
                 use_system_hosts=False, timeout=10, timeout_limit=3):
        """
        Create a new SSH connection wrapper.
        :param host:  Hostname of the Server  to connect to.
        :param port:  Ts3Server SSH port.
        :param username:  Serverquery username
        :param password:  Serverquery password
        :param accept_all_keys:  Accept all host keys (dangerous!) (default=false)
        :param host_key_file:  Path to the host key file to use (default=None)
        :param use_system_hosts:  Should the system known hosts be used? (default=False)
        :param timeout:  Timeout in seconds (default=10)
        :param timeout_limit:   How often a timeout is allowed to happen while reading before we
                                assume the server connection died. (default=3)
        """
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

    def read_until(self, delimiter, timeout=None):
        """
        Read until a given byte string, delimiter, or until  the timeout limit set is reached.
        The timeout parameter is ignored.
        """
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
                    continue
                if len(received) == 0:
                    raise TS3ConnectionClosedException("SSH connection was closed!")
                self._buffer += received
            else:
                break
        data = self._buffer[:delimiter_pos + len(delimiter)]
        self._buffer = self._buffer[delimiter_pos + len(delimiter):]
        return data

    def write(self, data):
        """
        Write bytes in data to the SSH connection.
        """
        try:
            self._channel.send(data)
        except OSError:
            raise TS3ConnectionClosedException(OSError)

    def close(self):
        """"
        Close the underlying SSH connection.
        """
        self._ssh_conn.close()
