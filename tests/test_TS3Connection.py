import logging
from unittest import TestCase
import sys
from ts3API.Events import *
from ts3API.TS3Connection import TS3Connection

class MockTS3Connection(TS3Connection):
    def __init__(self):
        self._logger = logging.Logger(__name__, logging.DEBUG)
        self._logger.addHandler(logging.StreamHandler())


# noinspection DuplicatedCode
class TestTS3Connection(TestCase):
    def setUp(self) -> None:
        self.conn = MockTS3Connection()

    def test_parse_resp_kicked_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=" + str(
            ReasonID.SERVER_KICK.value).encode("ascii") + b" reasonmsg=Kicked. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientKickedEvent, type(result), "Client kick not parsed correctly")
        self.assertEqual(1, result.client_id, "Client kick not parsed correctly")

    def test_parse_banned_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=" + str(ReasonID.BAN.value).encode(
            "ascii") + b" reasonmsg=Kicked. clid=1 bantime=10 invokerid=2 invokername=Test invokeruid=sdfsadf"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientBannedEvent, type(result), "Client ban not parsed correctly")
        self.assertEqual(1, result.client_id, "Client ban not parsed correctly")
        self.assertEqual(10, result.ban_time, "Client ban not parsed correctly")
        self.assertEqual(2, result.invoker_id, "Client ban not parsed correctly")
        self.assertEqual("Test", result.invoker_name, "Client ban not parsed correctly")
        self.assertEqual("sdfsadf", result.invoker_uid, "Client ban not parsed correctly")

    def test_parse_resp_left_event(self):
        resp = b"notifyclientleftview cfid=1 ctid=0 reasonid=8 " \
               b"reasonmsg=Left. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result), "ClientLeft not parsed correctly")
        self.assertEqual(result.client_id, 1, "ClientLeft not parsed correctly")

    def test_parse_resp_left_event_missing_reason_id(self):
        resp = b"notifyclientleftview reasonmsg=Left. clid=1"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result),
                      "ClientLeft without reason id not parsed correctly")
        self.assertEqual(1, result.client_id, "ClientLeft without reason id not parsed correctly")

    def test_parse_resp_left_event_empty(self):
        resp = b"notifyclientleftview"
        result = self.conn._parse_resp(resp)
        self.assertIs(ClientLeftEvent, type(result), "Empty client left not parsed correctly")
        self.assertEqual(-1, result.client_id, "Empty ClientLeft not parsed correctly")

    def test_parse_server_edited_event(self):
        resp = b"notifyserveredited reasonid=0 invokerid=1 invokername=test " \
               b"invokeruid=asdf virtualserver_name=new_name virtualserver_name_phonetic=neeew\\sname"
        result = self.conn._parse_resp(resp)
        self.assertIs(ServerEditedEvent, type(result), "ServerEdited Event not parsed correctly")
        assert result.invoker_id == "1"
        assert result.invoker_uid == "asdf"
        assert result.invoker_name == "test"
        assert result.reason_id == "0"
        p = result.changed_properties
        assert len(p) == 2
        assert p["virtualserver_name"] == "new_name"
        assert p["virtualserver_name_phonetic"] == "neeew name"
        

    def test_parse_server_edited_event_empty(self):
        resp = b"notifyserveredited"
        result = self.conn._parse_resp(resp)
        self.assertIs(ServerEditedEvent, type(result), "Empty ServerEdited Event not parsed correctly")
        assert result.invoker_id == "-1"
        assert result.invoker_uid == "-1"
        assert result.invoker_name == ""
        assert result.reason_id == ""
        p = result.changed_properties
        assert len(p) == 0
