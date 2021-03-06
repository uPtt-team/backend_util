class Console:
    run_mode_dev = 'dev'
    run_mode_release = 'release'

    server_mode_local = 'local'
    server_mode_cloud = 'cloud'

    role_server = 'server'
    role_client = 'client'

    def __init__(self):
        # dev
        # release

        self.run_mode = self.run_mode_dev
        self.server_mode = self.server_mode_local
        self.config = None
        self.event = None
        self.role = None
        self.ptt_adapter = None

        ##################################
        # client
        self.command = None
        self.dynamic_data = None

        self.login_token = None
        self.ptt_id = None
        self.ptt_pw = None
        self.dialogue = None
        self.token = None
        self.public_key = None
        self.private_key = None
        self.crypto = None
        self.process = None
        self.login_complete = False
        self.last_send_time = 0
        self.user_public_key = None

        ##################################
        # server

        self.token_list = None
        self.public_key_list = None
        self.ws_server = None
        self.server_command = None
        self.connect_list = None
        self.connect_time = None
        self.max_online = None
