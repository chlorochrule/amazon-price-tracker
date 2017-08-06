#-*- coding: utf-8 -*-
import os
import re
from bottle import route, request, run, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    PostbackEvent
)

from amazon import item_search
from line import get_response_message

ASIN_PATTERN = '([0-9]{10})|(B[A-Z0-9]{9})'

line_bot_api = LineBotApi(os.environ['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['CHANNEL_ACCESS_SECRET'])

is_inputing_price = {}
minimum_price = {}

@route('/callback', method='POST')
def callback():
    signature = request.get_header('X-Line-Signature')
    body = request.body

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, 'Invalid "X-Line-Signature"')

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    message = TextSendMessage(text='わけがわからないよ！')
    if is_inputing_price.get(event.source.user_id, False):
        price_mo = re.search('[0-9]+', event.message.text.replace(',', ''))
        if price_mo:
            price = price_mo.group()
            if 1 < price < minimum_price[event.source.user_id]:
                message = get_response_message('input_price_ok')
                is_inputing_price[event.source.user_id] = False
            else:
                message = get_response_message('input_price_range_ng', price=minimum_price[event.source.user_id]-1)
        else:
            message = get_response_message('input_price_style_ng')
    elif 'amazon.co.jp' in event.message.text:
        asin_mo = re.search('/' + ASIN_PATTERN, event.message.text)
        if asin_mo:
            asin = asin_mo.group().replace('/', '')
            message = get_response_message('sent_url_ok', asin=asin)
        else:
            message = get_response_message('sent_url_ng')
    elif re.match(ASIN_PATTERN, event.message.text):
        message = get_response_message('sent_url_ok', asin=event.message.text)
    else:
        message = get_response_message('search_product', query=event.message.text)

    line_bot_api.reply_message(
        event.reply_token,
        message
    )

@handler.add(PostbackEvent, message=TextMessage)
def handle_postback(event):
    asin = event.postback.data['asin']
    tracktype = event.postback.data['tracktype']
    price = int(event.postback.data['price'])
    message = TextSendMessage(text='追跡する値段を入力してね。\n範囲）1~{}'.format(price-1))

    line_bot_api.reply_message(
        event.reply_token,
        message
    )

    minimum_price[event.source.user_id] = price
    is_inputing_price[event.source.user_id] = True

if __name__ == '__main__':
    run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
