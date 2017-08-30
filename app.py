#-*- coding: utf-8 -*-
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    PostbackEvent
)

from line import MessageHandler, PostbackHandler

ASIN_PATTERN = '([0-9]{10})|(B[A-Z0-9]{9})'
URL_PATTERN = 'http[s]?://'

CHANNEL_ACCESS_TOKEN = os.environ['CHANNEL_ACCESS_TOKEN']
CHANNEL_ACCESS_SECRET = os.environ['CHANNEL_ACCESS_SECRET']

app = Flask(__name__)

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
webhook_handler = WebhookHandler(CHANNEL_ACCESS_SECRET)
message_handler = MessageHandler(line_bot_api)
postback_handler = PostbackHandler(line_bot_api)

is_inputing_price = {}
minimum_price = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        webhook_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@webhook_handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    message_handler.handle(event=event)

@webhook_handler.add(PostbackEvent)
def handle_postback(event):
    postback_handler.handle(event)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
