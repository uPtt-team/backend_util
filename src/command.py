import time
import threading
from datetime import datetime

from SingleLog.log import Logger

from backend_util.src.event import EventConsole
from backend_util.src.errorcode import ErrorCode
from backend_util.src.msg import Msg
from backend_util.src.console import Console
from backend_util.src.config import Config
from backend_util.src import util
from backend_util.src.tag import Tag


class Command:
    def __init__(self, console_obj, to_server: bool):

        self.console = console_obj
        self.logger = Logger('Command-' + ('Server' if to_server else 'Client'), self.console.config.log_level,
                             handler=self.console.config.log_handler)

        self.logger.show(Logger.INFO, '初始化', '啟動')

        self.login = False
        self.logout = False

        self.push_msg = list()

        self.login_id = None
        self.login_password = None
        self.logout = False
        self.close = False
        self.send_waterball_id = None
        self.send_waterball_content = None
        self.add_friend_id = None
        self.parameter = None
        self.res_msg = None

        self.to_server = to_server
        self.ptt_bot_lock = threading.Lock()
        self.max_online_lock = threading.Lock()

        self.server_api = [
            Msg.key_get_token,
            # Msg.key_update_public_key,
            Msg.key_login_success,
            Msg.key_logout_success,
            Msg.key_heartbeat,
            Msg.key_get_public_key
        ]

        self.logger.show(
            Logger.INFO,
            '初始化',
            '完成')

    def check_token(self, msg):
        if msg is None:
            return False
        if Msg.key_token not in msg.data:
            return False

        current_token = msg.data[Msg.key_token]

        return self.console.login_token == current_token

    def _get_token_thread(self):
        for e in self.console.event.event_chain[EventConsole.key_send_token]:
            self.res_msg = e(self.parameter)

    def _verify_hash(self, recv_msg, opt, ptt_id, key_value):

        timestamp = self.get_msg_value(recv_msg, Msg.key_timestamp)
        if timestamp is None:
            return False
        hash_value = self.get_msg_value(recv_msg, Msg.key_hash)
        if hash_value is None:
            return False

        current_time = int(time.time())
        if abs(current_time - timestamp) > Config.verify_time_threshold:
            self.logger.show(
                Logger.INFO,
                'current_time',
                current_time)

            self.logger.show(
                Logger.INFO,
                'timestamp',
                timestamp)

            self.logger.show(
                Logger.INFO,
                '時間驗證',
                '失敗')

            res_msg = Msg(
                operate=opt,
                code=ErrorCode.ErrorParameter,
                msg=f'Please check time')
            self.console.command.push(res_msg)
            return False

        current_token = self.console.token_list.get_value(ptt_id.lower())
        if current_token is None:
            self.logger.show(
                Logger.INFO,
                '取得 Token',
                '失敗')
            res_msg = Msg(
                operate=opt,
                code=ErrorCode.ErrorParameter,
                msg=f'Please require token first')
            self.console.command.push(res_msg)
            return False

        current_hash = util.get_verify_hash(timestamp, current_token, key_value)
        if current_hash != hash_value:
            self.logger.show(
                Logger.INFO,
                '雜湊值驗證',
                '失敗')
            res_msg = Msg(
                operate=opt,
                code=ErrorCode.ErrorParameter,
                msg=f'Verify fail')
            self.console.command.push(res_msg)
            return False

        return True

    def get_msg_value(self, msg, key):
        opt = msg.get(Msg.key_opt)

        value = msg.get(key)
        if value is None:
            res_msg = Msg(
                operate=opt,
                code=ErrorCode.ErrorParameter,
                msg=f'You must send {key}')
            self.console.command.push(res_msg)
            return None
        return value

    def analyze(self, recv_msg: Msg, ws):

        opt = self.get_msg_value(recv_msg, Msg.key_opt)
        if opt is None:
            return

        if self.console.role == Console.role_server:
            if opt not in self.server_api:
                res_msg = Msg(
                    operate=opt,
                    code=ErrorCode.ErrorParameter,
                    msg=f'{opt} not in server api list')
                self.console.command.push(res_msg)
                return
        else:
            self.logger.show(Logger.INFO, '收到訊息', opt)

        if opt == Msg.key_get_public_key:
            if self.console.role == Console.role_server:
                ptt_id = self.get_msg_value(recv_msg, Msg.key_ptt_id)
                if ptt_id is None:
                    return
                self.logger.show(Logger.INFO, '收到請求', ptt_id, opt)

                target = self.get_msg_value(recv_msg, Msg.key_target)
                if target is None:
                    return

                public_key = self.console.public_key_list.get_value(target.lower())
                if not public_key:
                    res_msg = Msg(
                        operate=opt,
                        code=ErrorCode.NoSuchUser,
                        msg=f'{target} is not using uPtt')
                    res_msg.add(Msg.key_target, target)
                else:
                    res_msg = Msg(
                        operate=opt,
                        code=ErrorCode.Success)
                    res_msg.add(Msg.key_target, target)
                    res_msg.add(Msg.key_public_key, public_key)
                self.console.command.push(res_msg)

            else:
                target = self.get_msg_value(recv_msg, Msg.key_target)
                if target is None:
                    return
                error_code = self.get_msg_value(recv_msg, Msg.key_code)
                if error_code is None:
                    return
                if target.lower() == self.console.ptt_id.lower():
                    self.console.process.wait_public_key_result = error_code
                else:
                    if error_code != ErrorCode.Success:
                        self.console.command.push(recv_msg)
                        return

                    public_key = self.get_msg_value(recv_msg, Msg.key_public_key)
                    if not public_key:
                        return
                    self.logger.show(Logger.INFO, 'target id', target)
                    self.logger.show(Logger.INFO, 'public_key', public_key)

                    self.console.user_public_key.set_value(target.lower(), public_key)

        elif opt == Msg.key_get_token:

            if self.console.role == Console.role_server:
                current_ptt_id = self.get_msg_value(recv_msg, Msg.key_ptt_id)
                if current_ptt_id is None:
                    return
                self.logger.show(Logger.INFO, '收到請求', current_ptt_id, opt)

                current_token = util.generate_token()

                ptt_id = self.console.config.get_value(Config.level_SYSTEM, Config.key_ptt_id)
                ptt_pw = self.console.config.get_value(Config.level_SYSTEM, Config.key_ptt_pw)

                self.ptt_bot_lock.acquire()
                try:
                    self.parameter = (ptt_id, ptt_pw, current_ptt_id, current_token)
                    t = threading.Thread(target=self._get_token_thread)
                    t.start()
                    t.join()
                finally:
                    self.ptt_bot_lock.release()

                # Update token
                self.console.token_list.set_value(current_ptt_id.lower(), current_token)
                self.push(self.res_msg)
            else:
                # {"operation": "server_get_token", "code": 0, "msg": "Success"}
                error_code = self.get_msg_value(recv_msg, Msg.key_code)
                if error_code is None:
                    return
                if error_code == ErrorCode.Success:
                    self.logger.show(Logger.INFO, '伺服器已經送出 token')
                    self.console.process.login_result = 'search_token'
                    self.console.event.execute(EventConsole.key_get_token)
                else:
                    # 送訊息到前端
                    self.console.command.push(recv_msg)

        elif opt == Msg.key_update_public_key:

            if self.console.role == Console.role_server:
                ptt_id = self.get_msg_value(recv_msg, Msg.key_ptt_id)
                if ptt_id is None:
                    return
                self.logger.show(Logger.INFO, '收到請求', ptt_id, opt)

                public_key = self.get_msg_value(recv_msg, Msg.key_public_key)
                if public_key is None:
                    return

                self.logger.show(
                    Logger.INFO,
                    'ptt_id',
                    ptt_id)

                self.logger.show(
                    Logger.INFO,
                    'public_key',
                    public_key)

                if not self._verify_hash(recv_msg, opt, ptt_id, public_key):
                    return

                self.console.public_key_list.set_value(ptt_id.lower(), public_key)

                res_msg = Msg(
                    operate=opt,
                    code=ErrorCode.Success,
                    msg='Update success')
                self.console.command.push(res_msg)
            else:
                self.console.event.execute(EventConsole.key_get_token)

        elif opt == Msg.key_login_success or opt == Msg.key_heartbeat:
            if self.console.role == Console.role_server:
                ptt_id = self.console.command.get_msg_value(recv_msg, Msg.key_ptt_id)
                if ptt_id is None:
                    return

                timestamp = self.get_msg_value(recv_msg, Msg.key_timestamp)
                if timestamp is None:
                    return

                if opt == Msg.key_login_success:
                    self.logger.show(Logger.INFO, '收到請求', ptt_id, opt)

                    public_key = self.get_msg_value(recv_msg, Msg.key_public_key)
                    if public_key is None:
                        return

                    if not self._verify_hash(recv_msg, opt, ptt_id, Msg.key_login_success + public_key):
                        return

                    self.console.public_key_list.set_value(ptt_id.lower(), public_key, show_result=False)
                else:
                    if not self._verify_hash(recv_msg, opt, ptt_id, Msg.key_heartbeat):
                        return

                self.max_online_lock.acquire()

                self.console.connect_list.set_value(ptt_id.lower(), ws, show_result=False)
                self.console.connect_time.set_value(ptt_id.lower(), timestamp, show_result=False)

                current_online = len(self.console.connect_list)
                current_time = self.console.max_online.get_value(current_online)
                if current_time is None:
                    date_time = datetime.fromtimestamp(timestamp)
                    self.console.max_online.set_value(current_online, str(date_time))

                self.max_online_lock.release()
            else:
                pass

        elif opt == Msg.key_login:

            payload = self.get_msg_value(recv_msg, Msg.key_payload)
            if payload is None:
                return
            ptt_id = self.get_msg_value(payload, Msg.key_ptt_id)
            if ptt_id is None:
                return
            ptt_pass = self.get_msg_value(payload, Msg.key_ptt_pass)
            if ptt_pass is None:
                return

            if self.console.login_complete:
                push_msg = Msg(
                    operate=Msg.key_login,
                    code=ErrorCode.Success,
                    msg='已經登入')
                self.console.command.push(push_msg)
                return

            self.logger.show(
                Logger.INFO,
                '執行登入程序')

            res_msg = None
            for e in self.console.event.event_chain[EventConsole.key_login]:
                current_res_msg = e(ptt_id, ptt_pass)
                if current_res_msg is None:
                    continue
                if current_res_msg.get(Msg.key_code) != ErrorCode.Success:
                    self.push(current_res_msg)
                    self.logger.show(
                        Logger.INFO,
                        '登入程序中斷')
                    return
                res_msg = current_res_msg
            if res_msg:
                self.push(res_msg)

            self.logger.show(
                Logger.INFO,
                '登入程序全數完成')

        elif opt == Msg.key_logout_success:
            if self.console.role == Console.role_server:
                ptt_id = self.get_msg_value(recv_msg, Msg.key_ptt_id)
                if ptt_id is None:
                    return
                self.logger.show(Logger.INFO, '收到請求', ptt_id, opt)

                self.max_online_lock.acquire()

                self.console.connect_list.set_value(ptt_id.lower(), None, show_result=False)
                self.console.connect_time.set_value(ptt_id.lower(), None, show_result=False)

                self.max_online_lock.release()

        elif opt == Msg.key_logout:
            if not self.console.login_complete:
                push_msg = Msg(
                    operate=Msg.key_login,
                    code=ErrorCode.Success,
                    msg='已經登出')
                self.console.command.push(push_msg)
                return

            self.logger.show(
                Logger.INFO,
                '執行登出程序')
            self.console.event.execute(EventConsole.key_logout)
            self.logger.show(
                Logger.INFO,
                '登出程序全數完成')

        elif opt == Msg.key_close:
            self.logger.show(
                Logger.INFO,
                '執行終止程序')
            self.console.event.execute(EventConsole.key_close)
            self.logger.show(
                Logger.INFO,
                '終止程序全數完成')

        elif opt == Msg.key_sendwaterball:
            if not self.check_token(recv_msg):
                self.logger.show(
                    Logger.INFO,
                    '權杖不相符')
                res_msg = Msg(
                    operate=opt,
                    code=ErrorCode.TokenNotMatch,
                    msg='Token not match')
                self.push(res_msg)
                return
            waterball_id = recv_msg.get(Msg.key_payload)[Msg.key_ptt_id]
            waterball_content = recv_msg.get(Msg.key_payload)[Msg.key_content]

            self.logger.show(
                Logger.INFO,
                '執行丟水球程序')
            self.console.event.execute(EventConsole.key_send_waterball, parameter=(waterball_id, waterball_content))
            self.logger.show(
                Logger.INFO,
                '丟水球程序全數完成')

        elif opt == 'getwaterballhistory':

            if not self.check_token(recv_msg):
                self.logger.show(
                    Logger.INFO,
                    'Token not match')
                res_msg = Msg(
                    operate=opt,
                    code=ErrorCode.TokenNotMatch,
                    msg='Token not match')
                self.push(res_msg)
                return

            target_id = recv_msg.data[Msg.key_payload][Msg.key_ptt_id]
            count = recv_msg.data[Msg.key_payload][Msg.key_count]

            if Msg.key_index in recv_msg.data[Msg.key_payload]:
                index = recv_msg.data[Msg.key_payload][Msg.key_index]
                history_list = self.console.dialogue.get(target_id, count, index=index)
            else:
                history_list = self.console.dialogue.get(target_id, count)

            current_res_msg = Msg(
                operate=opt,
                code=ErrorCode.Success,
                msg='Get history waterball success')

            payload = Msg()

            tag_name = Tag(self.console).get_tag(target_id)
            if tag_name is None:
                tag_name = ''

            payload.add(Msg.key_tag, tag_name)
            payload.add(Msg.key_list, history_list)
            current_res_msg.add(Msg.key_payload, payload)

            self.push(current_res_msg)
        elif opt == 'addfriend':
            self.add_friend_id = recv_msg.get(Msg.key_payload)[Msg.key_ptt_id]

        else:
            if self.to_server:
                self.logger.show(
                    Logger.INFO,
                    '收到來自伺服器不明訊息',
                    opt)
            else:
                current_res_msg = Msg(
                    operate=opt,
                    code=ErrorCode.Unsupported,
                    msg='Unsupported')
                self.push(current_res_msg)

    def push(self, push_msg):
        self.push_msg.append(push_msg.__str__())
