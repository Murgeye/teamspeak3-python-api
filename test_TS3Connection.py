from unittest import TestCase
import logging

from .Events import ClientLeftEvent, ReasonID, ClientKickedEvent, ClientBannedEvent
from .TS3Connection import TS3Connection


class MockTS3Connection(TS3Connection):
    def __init__(self):
        self._logger = logging.Logger(__name__, logging.DEBUG)
        self._logger.addHandler(logging.StreamHandler())


# noinspection DuplicatedCode
class TestTS3Connection(TestCase):
    def setUp(self) -> None:
        self.conn = MockTS3Connection()

    def test_parse_resp_left_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=8 " \
               b"reasonmsg=Left. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result), "ClientLeft not parsed correctly")
        self.assertEqual(result.client_id, 1, "ClientLeft not parsed correctly")

    def test_parse_resp_kicked_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=" + str(ReasonID.SERVER_KICK.value).encode("ascii") +\
               b" reasonmsg=Kicked. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientKickedEvent, type(result), "Client kick not parsed correctly")
        self.assertEqual(1, result.client_id, "Client kick not parsed correctly")

    def test_parse_banned_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=" + str(ReasonID.BAN.value).encode("ascii") + \
               b" reasonmsg=Kicked. clid=1 bantime=10 invokerid=2 invokername=Test invokeruid=sdfsadf"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientBannedEvent, type(result), "Client ban not parsed correctly")
        self.assertEqual(1, result.client_id, "Client ban not parsed correctly")
        self.assertEqual(10, result.ban_time, "Client ban not parsed correctly")
        self.assertEqual(2, result.invoker_id, "Client ban not parsed correctly")
        self.assertEqual("Test", result.invoker_name, "Client ban not parsed correctly")
        self.assertEqual("sdfsadf", result.invoker_uid, "Client ban not parsed correctly")

    def test_parse_resp_left_event_missing_reason_id(self):
        resp = b"notifyclientleftview reasonmsg=Left. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result), "ClientLeft without reason id not parsed correctly")
        self.assertEqual(1, result.client_id, "ClientLeft without reason id not parsed correctly")

    def test_parse_resp_left_event_empty(self):
        resp = b"notifyclientleftview"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result), "Empty client left not parsed correctly")
        self.assertEqual(-1, result.client_id, "Empty ClientLeft not parsed correctly")
