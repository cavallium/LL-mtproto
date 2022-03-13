import asyncio
import logging
import random
import time
import traceback
import typing

from .constants import TelegramDatacenter, _TelegramDatacenterInfo
from .network import mtproto
from .network.mtproto import AuthKey, MTProto
from .tl.tl import Structure


class _PendingRequest:
    response: asyncio.Future
    request: dict

    def __init__(self, loop: asyncio.AbstractEventLoop, message: dict):
        self.response = loop.create_future()
        self.request = message


class Client:
    _seq_no: int
    _mtproto: mtproto.MTProto | None
    _loop: asyncio.AbstractEventLoop
    _msgids_to_ack: list[int]
    _last_time_acks_flushed: float
    _last_seqno: int
    _stable_seqno: bool
    _seqno_increment: int
    _mtproto_loop_task: asyncio.Task | None
    _pending_requests: dict[int, _PendingRequest]
    _pending_pongs: dict[int, asyncio.TimerHandle]
    _datacenter: _TelegramDatacenterInfo
    _auth_key: AuthKey
    _pending_ping_request: asyncio.TimerHandle | None

    def __init__(self, datacenter: TelegramDatacenter, auth_key: AuthKey):
        self._seq_no = -1
        self._mtproto = None
        self._loop = asyncio.get_event_loop()
        self._msgids_to_ack = []
        self._last_time_acks_flushed = time.time()
        self._last_seqno = 0
        self._stable_seqno = False
        self._seqno_increment = 1
        self._mtproto_loop_task = None
        self._pending_requests = dict()
        self._pending_pongs = dict()
        self._datacenter = typing.cast(_TelegramDatacenterInfo, datacenter.value)
        self._auth_key = auth_key
        self._pending_ping_request = None

    async def rpc_call(self, message: dict[str, any]) -> dict[str, any]:
        if "_cons" not in message:
            raise RuntimeError("`_cons` attribute is required in message object")

        pending_request = _PendingRequest(self._loop, message)
        return await self._rpc_call(pending_request)

    async def _rpc_call(self, pending_request: _PendingRequest, no_response: bool = False) -> dict[str, any] | None:
        if self._mtproto is None or self._mtproto_loop_task.done():
            await self._start_mtproto_loop()

        await self._flush_msgids_to_ack()
        seqno = self._get_next_odd_seqno()

        message_id, write_future = self._mtproto.write(seqno, **pending_request.request)
        constructor = pending_request.request["_cons"]

        logging.log(logging.DEBUG, "sending message (%s) %d to mtproto", constructor, message_id)

        self._pending_requests[message_id] = pending_request

        try:
            await asyncio.wait_for(write_future, 120)
        except (OSError, asyncio.CancelledError, KeyboardInterrupt):
            self._delete_pending_request(message_id)

        self._seqno_increment += 1

        if no_response:
            self._loop.call_later(600, self._delete_pending_request, message_id)
        else:
            return await asyncio.wait_for(pending_request.response, 600)

    async def _start_mtproto_loop(self):
        self._delete_all_pending_data()

        if self._mtproto is not None:
            self._mtproto_loop_task.cancel()
            self._mtproto.stop()

        logging.log(logging.DEBUG, "connecting to Telegram at %s", self._datacenter)

        self._mtproto = MTProto(self._datacenter.address, self._datacenter.port, self._datacenter.rsa, self._auth_key)

        self._mtproto_loop_task = self._loop.create_task(self._mtproto_loop())
        await self._create_new_ping_request()

    def _create_new_ping_request_sync(self):
        self._loop.create_task(self._create_new_ping_request())

    async def _create_new_ping_request(self):
        new_random_ping_id = random.randrange(-2 ** 63, 2 ** 63)
        seqno = self._get_next_odd_seqno()

        request = dict(_cons="ping", ping_id=new_random_ping_id)
        pending_request = _PendingRequest(self._loop, request)

        self._pending_pongs[new_random_ping_id] = self._loop.call_later(10, self.disconnect)

        message_id, write_future = self._mtproto.write(seqno, **request)
        self._pending_requests[message_id] = pending_request

        await asyncio.wait_for(write_future, 120)

    def _get_next_odd_seqno(self) -> int:
        self._last_seqno = ((self._last_seqno + 1) // 2) * 2 + 1
        return self._last_seqno

    def _get_next_even_seqno(self) -> int:
        self._last_seqno = (self._last_seqno // 2 + 1) * 2
        return self._last_seqno

    def _delete_all_pending_pongs(self):
        for pending_pong_id in self._pending_pongs.keys():
            self._delete_pending_pong(pending_pong_id, False)

        self._pending_pongs.clear()

    def _delete_all_pending_requests(self):
        for pending_request_id in self._pending_requests.keys():
            self._delete_pending_request(pending_request_id, False)

        self._pending_requests.clear()

    def _delete_pending_pong(self, ping_id: int, remove: bool = True):
        if ping_id in self._pending_pongs:
            self._pending_pongs[ping_id].cancel()

            if remove:
                del self._pending_pongs[ping_id]

    def _delete_pending_request(self, msg_id: int, remove: bool = True):
        if msg_id in self._pending_requests:
            pending_response = self._pending_requests[msg_id].response

            if not pending_response.done():
                pending_response.set_exception(InterruptedError())

            if remove:
                del self._pending_requests[msg_id]

    async def _mtproto_loop(self):
        while self._mtproto:
            try:
                message = await self._mtproto.read()
            except:
                logging.log(logging.ERROR, "failure while read message from mtproto: %s", traceback.format_exc())
                break

            logging.log(logging.DEBUG, "received message %d from mtproto", message.msg_id)

            try:
                await self._process_telegram_message(message)
                await self._flush_msgids_to_ack_if_needed()
            except:
                logging.log(logging.ERROR, "failure while process message from mtproto: %s", traceback.format_exc())

    def _delete_all_pending_data(self):
        self._delete_all_pending_pongs()
        self._delete_all_pending_requests()

        if self._pending_ping_request is not None:
            self._pending_ping_request.cancel()

        self._pending_ping_request = None

    async def _flush_msgids_to_ack_if_needed(self):
        if len(self._msgids_to_ack) >= 32 or (time.time() - self._last_time_acks_flushed) > 10:
            await self._flush_msgids_to_ack()

    async def _process_telegram_message(self, message: Structure):
        self._update_last_seqno_from_incoming_message(message)

        body = message.body.packed_data if message.body == "gzip_packed" else message.body

        if body == "msg_container":
            for m in body.messages:
                await self._process_telegram_message(m)

        else:
            await self._process_telegram_message_body(body)
            await self._acknowledge_telegram_message(message)

    async def _process_telegram_message_body(self, body: Structure):
        if body == "rpc_result":
            self._process_rpc_result(body)

        if body == "pong":
            self._process_pong(body)

        if body == "bad_server_salt":
            await self._process_bad_server_salt(body)

        if body == "bad_msg_notification" and body.error_code == 32 and not self._stable_seqno:
            await self._process_bad_msg_notification_msg_seqno_too_low(body)

    def _process_pong(self, pong: Structure):
        logging.log(logging.DEBUG, "pong message: %d", pong.ping_id)

        self._delete_pending_pong(pong.ping_id)

        if pong.msg_id in self._pending_requests:
            self._pending_requests[pong.msg_id].response.set_result({})

        self._pending_ping_request = self._loop.call_later(10, self._create_new_ping_request_sync)

    async def _acknowledge_telegram_message(self, message: Structure):
        if message.seqno % 2 == 1:
            self._msgids_to_ack.append(message.msg_id)
            await self._flush_msgids_to_ack()

    async def _flush_msgids_to_ack(self):
        self._last_time_acks_flushed = time.time()

        if not self._msgids_to_ack or not self._stable_seqno:
            return

        seqno = self._get_next_even_seqno()
        _, write_future = self._mtproto.write(seqno, _cons="msgs_ack", msg_ids=self._msgids_to_ack)
        await asyncio.wait_for(write_future, 120)
        self._msgids_to_ack = []

    def _update_last_seqno_from_incoming_message(self, message: Structure):
        self._last_seqno = max(self._last_seqno, message.seqno)

    async def _process_bad_server_salt(self, body: Structure):
        if self._mtproto.get_server_salt != 0:
            self._stable_seqno = False

        self._mtproto.set_server_salt(body.new_server_salt)
        logging.log(logging.DEBUG, "updating salt: %d", body.new_server_salt)

        if body.bad_msg_id in self._pending_requests:
            bad_request = self._pending_requests[body.bad_msg_id]
            del self._pending_requests[body.bad_msg_id]
            await self._rpc_call(bad_request, no_response=True)

        else:
            logging.log(logging.DEBUG, "bad_msg_id %d not found", body.bad_msg_id)

    async def _process_bad_msg_notification_msg_seqno_too_low(self, body: Structure):
        self._seqno_increment = min(2 ** 31 - 1, self._seqno_increment << 1)
        self._last_seqno += self._seqno_increment

        logging.log(logging.DEBUG, "updating seqno by %d to %d", self._seqno_increment, self._last_seqno)

        if body.bad_msg_id in self._pending_requests:
            bad_request = self._pending_requests[body.bad_msg_id]
            del self._pending_requests[body.bad_msg_id]
            await self._rpc_call(bad_request, no_response=True)

    def _process_rpc_result(self, body: Structure):
        self._stable_seqno = True

        if body.req_msg_id in self._pending_requests:
            pending_request = self._pending_requests[body.req_msg_id]
            del self._pending_requests[body.req_msg_id]

            if body.result == "gzip_packed":
                result = body.result.packed_data
            else:
                result = body.result

            pending_request.response.set_result(result.get_dict())

    def disconnect(self):
        self._delete_all_pending_data()

        if self._mtproto is not None:
            self._mtproto_loop_task.cancel()
            self._mtproto.stop()

        self._mtproto = None
        self._mtproto_loop_task = None

    def __del__(self):
        if self._mtproto is not None:
            logging.log(logging.CRITICAL, "client %d not disconnected", id(self))
