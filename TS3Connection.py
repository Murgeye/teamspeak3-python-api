"""Main TS3Api File"""
import logging
import socket
import sys
import telnetlib
import threading
import time
import traceback

import blinker

from . import Events
from . import utilities
from .Events import TS3Event
from .TS3QueryExceptionType import TS3QueryExceptionType
from .utilities import TS3Exception, TS3ConnectionClosedException


class TS3Connection:
    """
    Connection class for the TS3 API. Uses a telnet connection to send messages to and receive
    messages from the Teamspeak 3 server.
    """

    def __init__(self, host="127.0.0.1", port=10011, log_file="api.log", use_ssh=False,
                 username=None, password=None, accept_all_keys=False, host_key_file=None,
                 use_system_hosts=False, sshtimeout=None, sshtimeoutlimit=3):
        """
        Creates a new TS3Connection.
        :param host: Host to connect to. Can be an IP address or a hostname.
        :param port: Port to connect to.
        :param use_ssh: Should an encrypted ssh connection be used?
        :type host: str
        :type port: int
        :type use_ssh: bool
        """
        self._is_ssh = use_ssh
        self._conn_lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        self._logger.propagate = 0
        self._logger.setLevel(logging.WARNING)
        self.stop_recv = threading.Event()
        self._new_data = threading.Event()
        self._data_read = threading.Event()
        self._data_read.set()
        self._data = None
        # create console handler and set level to warning
        file_handler = logging.FileHandler(log_file, mode='a+')
        file_handler.setLevel(logging.WARNING)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # add formatter to ch
        file_handler.setFormatter(formatter)

        # add ch to logger
        self._logger.addHandler(file_handler)

        if not use_ssh:
            self._conn = telnetlib.Telnet(host, port, timeout=socket.getdefaulttimeout())
            self._logger.debug(self._conn.read_until(b"\n\r"))
            self._logger.debug(self._conn.read_until(b"\n\r"))
        else:
            from .SSHConnWrapper import SSHConnWrapper
            self._conn = SSHConnWrapper(host, port, username, password,
                                        accept_all_keys=accept_all_keys,
                                        host_key_file=host_key_file, timeout=sshtimeout,
                                        timeout_limit=sshtimeoutlimit,
                                        use_system_hosts=use_system_hosts)
            self._logger.debug(self._conn.read_until(b"\n\r"))
            self._logger.debug(self._conn.read_until(b"\n\r"))
        threading.Thread(target=self._recv).start()
        if username is not None and password is not None and not use_ssh:
            self.login(username, password)

    def login(self, user, password):
        """
        Login with query credentials.
        :param user: Username to login with.
        :param password: Password to login with.
        :type user: str
        :type password: str
        """
        if self._is_ssh:
            self._logger.warning("Ignoring login command on ssh connection.")
        else:
            self._send("login", [user, password])

    def use(self, sid):
        """
        Chose the virtual server to use.
        :param sid: SID of the virtual server to use.
        :type sid: int
        """
        self._send("use", [str(sid)])

    def clientlist(self, params=None):
        """
        Get a clientlist from the server.
        :param params: List of parameters strings to use.
        :type params: list[str]
        :return: List of clients
        """
        if params is None:
            params = []
        args = list()
        for param in params:
            args.append("-" + param)
        clist = self._send("clientlist", args)
        clients = TS3Connection._parse_resp_to_list_of_dicts(clist)
        if len(clients) == 0:
            self._logger.warning("Clientlist empty %s", str(clist))
        return clients

    def _send(self, command, args=None, wait_for_resp=True, log_keepalive=False):
        """
        :param command: Command to send.
        :param args: Parameter to send, will be escaped.
        :param wait_for_resp: True: Expects at least a error line and blocks until one is received.
                              False: Almost exclusively for keepalive, doesn't wait for an
                                     acknowledgment.
        :param log_keepalive: Should keepalive messages be logged?
        :return: Query response, if one was received.
        :rtype: bytes | None
        :type command: str
        :type args: list[str]
        :type wait_for_resp: bool
        :type log_keepalive: bool
        """
        query = command
        saved_resp = b''
        ack = False
        if args is None:
            args = []
        for arg in args:
            query += " " + utilities.escape(arg)
        query += "\n\r"
        query = query.encode()
        resp = None
        try:
            self._logger.debug("Trying to acquire lock")
            if self._conn_lock.acquire():
                self._logger.debug("Lock acquired")
                if not query == b'\n\r' or query == b'\n\r' and log_keepalive:
                    self._logger.debug("Query: %s", str(query))
                self._logger.debug("Writing to connection")
                self._conn.write(query)
                self._logger.debug("Written to connection")
                if not wait_for_resp:
                    self._conn_lock.release()
                    return None
                while not ack:
                    while resp is None:
                        self._new_data.wait()
                        resp = self._data
                        self._new_data.clear()
                        self._data_read.set()
                        if resp is not None:
                            if resp[0] == b'error':
                                ack = True
                                if resp[1] != b'id=0':
                                    raise TS3QueryException(
                                        int(resp[1].decode(encoding='UTF-8').split("=", 1)[1]),
                                        resp[2].decode(encoding='UTF-8').split("=", 1)[1])
                            else:
                                self._logger.debug("Resp: %s", str(resp))
                                saved_resp += resp
                                resp = None
        finally:
            self._conn_lock.release()
            self._logger.debug("Lock released")
        self._logger.debug("Saved resp: %s", str(saved_resp))
        return saved_resp

    def _recv(self):
        """
        Actual receiving, receives until \n\r is encountered. \n\r is cut from the end of the
        response.
        :return: Parsed response, split by " " or None if received message was an event.
        :rtype: bytes | None
        """
        while not self.stop_recv.is_set():
            try:
                self._logger.debug("Read until started")
                resp = self._conn.read_until(b"\n\r")[:-2]
                self._logger.debug("Read until ended")
            except (EOFError, TS3ConnectionClosedException) as _:
                self._logger.exception("Connection closed")
                if self.stop_recv.is_set():
                    self._conn.close()
                    return
                self._new_data.set()
                self.stop_recv.set()
                try:
                    self._conn.close()
                    self._logger.debug(
                        "Releasing lock for closed connection to unfreeze threads ...")
                    self._conn_lock.release()
                except:
                    pass
                continue
            self._logger.debug("Response: %s", str(resp))
            data = self._parse_resp(resp)
            self._logger.debug("Data: %s", str(data))
            if isinstance(data, TS3Event):
                event = data
                if isinstance(event, Events.TextMessageEvent):
                    signal = blinker.signal(event.event_type.name + "_" + event.targetmode.lower())
                else:
                    signal = blinker.signal(event.event_type.name)
                self._logger.debug("Sending signal")
                threading.Thread(target=signal.send, kwargs={'event': event}).start()
                continue
            if data is not None:
                self._data_read.wait()
                self._data = data
                self._data_read.clear()
                self._new_data.set()

    @staticmethod
    def _parse_resp_to_dict(resp):
        """
        Splits a response by " " and saves it in a dictionary.
        :type resp: bytes
        :param resp: Message to parse.
        :return: Dictionary containing all info extracted from the response.
        :rtype: dict[str, str]
        """
        resp = resp.decode(encoding='UTF-8').split(" ")
        info = dict()
        for part in resp:
            split = part.split('=', 1)
            # TODO: Handle empty data?
            if len(split) == 2:
                key, value = split
                info[key] = utilities.unescape(value)
        return info

    @staticmethod
    def _parse_resp_to_list_of_dicts(resp):
        """
        Parses multiple elements in a message into a list of dictionaries containing the info for
        each element.
        :type resp: bytes
        :param resp: Message to parse.
        :return: List of dictionaries containing the info.
        :rtype: list[dict[str, str]]
        """
        # Multiple responses are split by "|"
        split_list = resp.split(b"|")
        dict_list = list()
        for response in split_list:
            if len(response) > 0:
                dict_list.append(TS3Connection._parse_resp_to_dict(response))
        return dict_list

    def register_for_server_messages(self, event_listener=None, weak_ref=True):
        """
        Register the event_listener for server message events. Be careful, you should ignore your
        own messages by comparing the invoker_id to your client id ...
        :param event_listener: Blinker signal handler function to be informed:
                               on_event(sender, **kw), kw will contain the event
        :param weak_ref: Use weak refs for blinker, causing eventlisteners that go out of scope to
                         be removed (breaks nested functions)
        :type event_listener: (str, dict[str, any]) -> None
        :type weak_ref: bool
        """
        self._send("servernotifyregister", ["event=textserver"])
        if event_listener is not None:
            for event in Events.text_events:
                blinker.signal(event.name + "_server").connect(event_listener, weak=weak_ref)

    def register_for_channel_messages(self, event_listener=None, weak_ref=True):
        """
        Register the event_listener for channel message events. Be careful, you should ignore your
        own messages by comparing the invoker_id to your client id ...
        :param event_listener: Blinker signal handler function to be informed:
                               on_event(sender, **kw), kw will contain the event
        :param weak_ref: Use weak refs for blinker, causing eventlisteners that go out of scope to
                         be removed (breaks nested functions)
        :type event_listener: (str, dict[str, any]) -> None
        :type weak_ref: bool
        """
        self._send("servernotifyregister", ["event=textchannel"])
        if event_listener is not None:
            for event in Events.text_events:
                blinker.signal(event.name + "_channel").connect(event_listener, weak=weak_ref)

    def register_for_private_messages(self, event_listener=None, weak_ref=True):
        """
        Register the event_listener for private message events. Be careful, you should ignore your
        own messages by comparing the invoker_id to your client id ...
        :param event_listener: Blinker signal handler function to be informed:
                               on_event(sender, **kw), kw will contain
        the event
        :param weak_ref: Use weak refs for blinker, causing eventlisteners that go out of scope to
                         be removed (breaks nested functions)
        :type event_listener: (str, dict[str, any]) -> None
        :type weak_ref: bool
        """
        self._send("servernotifyregister", ["event=textprivate"])
        if event_listener is not None:
            for event in Events.text_events:
                blinker.signal(event.name + "_private").connect(event_listener, weak=weak_ref)

    def register_for_server_events(self, event_listener=None, weak_ref=True):
        """
        Register event_listener for receiving server_events.
        :param event_listener: Blinker signal handler function to be informed:
                               on_event(sender, **kw), kw will contain the event
        :type event_listener: (str, dict[str, any]) -> None
        :param weak_ref: Use weak refs for blinker, causing eventlisteners that go out of scope to
                         be removed (breaks nested functions)
        :type weak_ref: bool
        """
        self._send("servernotifyregister", ["event=server"])
        if event_listener is not None:
            for event in Events.server_events:
                blinker.signal(event.name).connect(event_listener, weak=weak_ref)

    def register_for_channel_events(self, channel_id, event_listener=None, weak_ref=True):
        """
        Register event_listener for receiving channel_events.
        :param event_listener:  Blinker signal handler function to be informed:
                                on_event(sender, **kw), kw will contain the event
        :param channel_id: Channel to register to, use 0 for all channels
        :param weak_ref:    Use weak refs for blinker, causing event_listeners that go out of scope
                            to be removed
        (breaks nested functions)
        :type channel_id: int | string
        :type event_listener: (str, dict[str, any]) -> None
        :type weak_ref: bool
        """
        self._send("servernotifyregister", ["event=channel", "id=" + str(channel_id)])
        if event_listener is not None:
            for event in Events.channel_events:
                blinker.signal(event.name).connect(event_listener, weak=weak_ref)

    def register_for_unknown_events(self, event_listener=None, weak_ref=True):
        """
        Register the event_listener for unknown events. Note: This will not actually call any register
        function, but will only add the event_listener to the list of functions to inform on unknown
        events. _event_type will hold the event type sent by the server.
        :param event_listener: Blinker signal handler function to be informed:
                               on_event(sender, **kw), kw will contain the event
        :param weak_ref: Use weak refs for blinker, causing eventlisteners that go out of scope to
                         be removed (breaks nested functions)
        :type event_listener: (str, dict[str, any]) -> None
        :type weak_ref: bool
        """
        if event_listener is not None:
            blinker.signal("UNKNOWN").connect(event_listener, weak=weak_ref)

    def clientmove(self, channel_id, client_id):
        """
        Move a client to another channel.
        :param channel_id: Channel to move client to.
        :param client_id: Id of the client to move.
        :type channel_id: int
        :type client_id: int
        """
        self._send("clientmove", ["cid=" + str(channel_id), "clid=" + str(client_id)])

    def clientupdate(self, params=None):
        """
        Update the query clients data.
        :param params: List of parameters to update in the form param=value.
        :type params: list[str]
        """
        if params is None:
            params = []
        self._send("clientupdate", params)

    def clientkick(self, client_id, reason_id, reason_msg):
        """
        Kick a client from the server.
        :param client_id: Client id of the user to kick.
        :type client_id: int
        :param reason_id: 4 - kick from channel 5 - kick from Server
        :type reason_id: int
        :param reason_msg: Message to send on kick, max. 40 characters
        :type reason_msg: str
        """
        self._send("clientkick", ["clid=" + str(client_id), "reasonid=" + str(reason_id),
                                  "reasonmsg=" + str(reason_msg)])

    def whoami(self):
        """
        Returns info of the query client.
        :return: Dictionary of query client information.
        :rtype: dict[str, str]
        """
        who = TS3Connection._parse_resp_to_dict(self._send("whoami", []))
        self._logger.info("Whoami: %s", str(who))
        return who

    def channellist(self, params=None):
        """
                Returns the channel listt.
                :param params: Optional parameters as defined by the serverquery manual.
                :return:  List of channels
        """
        if params is None:
            params = []
        args = list()
        for param in params:
            args.append("-" + param)
        channel_list = self._send("channellist", args)
        channels = TS3Connection._parse_resp_to_list_of_dicts(channel_list)
        if len(channels) == 0:
            self._logger.warning("Channellist empty %s", str(channel_list))
        return channels

    def channel_name_list(self):
        """
                    Returns a liszt of channel names. (Convenience Wrapper around channellist)
                    :return:  List of channel names
                  """
        names = list()
        channels = self.channellist()
        for channel in channels:
            names.append(channel.get("channel_name", ""))
        return names

    def channelfind(self, pattern):
        """
        Returns all channels with a name corresponding to pattern.
        :param pattern: Pattern to look for.
        :return: List of channels.
        :rtype: list[dict[str, str]]
        """
        return TS3Connection._parse_resp_to_list_of_dicts(
            self._send("channelfind", ["pattern=" + pattern]))

    def channelfind_by_name(self, name):
        """
        Returns all channels with a name that is exactly the same as the given name.
        :param name: Name to look for.
        :return: List of channels
        :rtype: list[dict[str, str]]
        """
        channel_candidates = self.channelfind(name)
        channel_list = list()
        for candidate in channel_candidates:
            if candidate.get("channel_name", "") == name:
                channel_list.append(candidate)
        return channel_list

    def sendtextmessage(self, targetmode, target, msg):
        """
        Sends a textmessage to the specified target.
        :param targetmode: 1: private message 2: textchannel 3: servertext
        :param target: client_id/channel_id
        :param msg: Message to send.
        :type targetmode: int
        :type target: int
        :type msg: str
        """
        self._send("sendtextmessage",
                   ["targetmode=" + str(targetmode), "target=" + str(target), "msg=" + str(msg)])

    def servergrouplist(self):
        """
        Returns a list of all servergroups with corresponding info.
        :return: List of servergroups.
        :rtype: list[dict[str, str]]
        """
        return TS3Connection._parse_resp_to_list_of_dicts(self._send("servergrouplist"))

    def find_servergroup_by_name(self, name):
        """
        Returns the servergroup with the specified name.
        :param name: Name to look for.
        :return: Server Group.
        :rtype: dict[str, str]
        """
        server_group_list = self.servergrouplist()
        for server_group in server_group_list:
            if server_group["name"] == name:
                return server_group

    def clientinfo(self, client_id):
        """
        Returns clientinfo for a client specified by its id.
        :param client_id: Id of the client.
        :return: Dictionary of client information.
        :rtype: dict[str,str]
        """
        return self._parse_resp_to_dict(self._send("clientinfo", ["clid=" + str(client_id)]))

    def clientpoke(self, clid, msg):
        """
        Pokes a client with a message.
        :param clid: client_id of the client to poke
        :param msg: Message to send.
        :type clid: int
        :type msg: str
        """
        return self._parse_resp_to_dict(self._send("clientpoke", ["clid=" + str(clid), "msg=" + str(msg)]))

    def _parse_resp(self, resp):
        """
        Parses a response. Messages starting with notify... are handled as events and the connected
        listeners are informed. Messages starting with error are split by " " and returned, all
        other messages will just be returned as is and can be handled by the caller.
        :param resp: Message to parse.
        :type resp: byte
        :return:    None if message notifies of an event, dictionary containing id and message on
                    acknowledgements and bytes on any other message.
        :rtype: None | dict[str, str] | bytes
        """
        # Acknowledgements
        if resp.startswith(b'error'):
            resp = resp.split(b' ')
            return resp
        # Events
        if resp.startswith(b'notify'):
            event = dict()
            event_type = "Unknown"
            try:
                resp = resp.decode(encoding='UTF-8').split(" ")
                event_type = resp[0]
                for info in resp[1:]:
                    split = info.split('=', 1)
                    if len(split) == 2:
                        key, value = split
                        event[key] = utilities.unescape(value)
                event = Events.EventParser.parse_event(event, event_type)
                return event
            except:
                self._logger.error("Error parsing event")
                self._logger.error(resp)
                self._logger.error("%s , %s", str(event), str(event_type))
                self._logger.error("\n\n")
                self._logger.error("Uncaught exception: %s", str(sys.exc_info()[0]))
                self._logger.error(str(sys.exc_info()[1]))
                self._logger.error(traceback.format_exc())
                return None
        # Query-Responses and other things(What could these be?)
        else:
            return resp

    def _recv_wait_timeout(self, timeout=0.1):
        """
        Like receives, but only reads for timeout seconds. If no info is received, the function
        returns, otherwise it reads a whole line before returning. This is used for receiving notify
        messages.
        :param timeout: Seconds to wait before returning if no message was received.
        :return:    None if nothing was received, parsed response corresponding to _parse_resp
                    otherwise.
        :rtype: None | dict[str, str] | bytes
        """
        resp = self._conn.read_until(b"\n\r", timeout)
        if len(resp) > 0 and not resp.endswith(b"\n\r"):
            resp += self._conn.read_until(b"\n\r")[:-2]
        if len(resp) > 0:
            self._logger.debug("No wait Response: %s", str(resp))
            return self._parse_resp(resp)

    def _send_keepalive(self):
        """
        Sends a keepalive message to the server to prevent timeout. Keepalive message is "\n\r".
        """
        self._send("whoami", wait_for_resp=True)

    def keepalive_loop(self, interval=5):
        """
        Sends keepalive messages every interval seconds and checks for new messages. Runs until
        self.stop_recv is set.
        :param interval: Seconds to wait between keepalive messages.
        :type interval: int
        """
        while not self.stop_recv.wait(interval):
            self._send_keepalive()
            time.sleep(interval)

    def quit(self):
        """
        Stops the connection from receiving and sends the quit signal.
        """
        # Avoid unclean exit by interfering with response to pending query
        if self._conn_lock.acquire():
            self.stop_recv.set()
        self._conn_lock.release()
        self._send("quit")

    def start_keepalive_loop(self, interval=5):
        """
        Starts a thread that sends keepalive messages every interval seconds.
        :param interval: Seconds between to keepalive messages.
        :return:
        """
        threading.Thread(target=self.keepalive_loop, args=(interval,)).start()

    def __getattr__(self, item):
        """
        manages unknown functions by sending command to ts3server
        inspired by rpc communication
        e.g. usage for 'clientdblist start=1 -count': ts3conn.clientdblist(start=1, 'count')
        :param item: name of the function
        :return: wrapper
        """

        def wrapper(*args, **kwargs):
            """
            This function sends the unknown call to ts3 like rpc.
            If response is received it will be returned
            :param args: list of parameters within the function head
            :param kwargs: dict of labeled parameters within the function head
            :return: (List of) Dictionary response or nothing, depends on ts3server response
            """
            resp = self._send(item,
                              ['-{}'.format(x) for x in args] + ['{}={}'.format(x[0], x[1]) for x in
                                                                 kwargs.items()])
            if resp:
                parsed_resp = self._parse_resp_to_list_of_dicts(resp)
                return parsed_resp[0] if len(parsed_resp) == 1 else parsed_resp

        return wrapper


class TS3QueryException(TS3Exception):
    """
    Query exception class to signalize failed queries and connection errors.
    """

    def __init__(self, error_id, message):
        """
        Creates a new QueryException.
        :param error_id: Id of the error.
        :param message: Error message.
        :type error_id: int
        :type message: str
        """
        self._type = TS3QueryExceptionType(error_id)
        self._msg = utilities.unescape(message)
        super(TS3QueryException, self).__init__(
            "Query failed with id=" + str(error_id) + " msg=" + str(self._msg))

    @property
    def message(self):
        return self._msg

    @property
    def type(self):
        return self._type

    @property
    def id(self):
        return self._type.numerator
