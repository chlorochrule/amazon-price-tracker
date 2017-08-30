#-*- coding: utf-8 -*-
import os
from functools import reduce
import psycopg2 as pg
from urllib import parse
from threading import Thread, Event

from linebot import LineBotApi
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    ConfirmTemplate,
    PostbackTemplateAction
)

from db import update_table
from amazon import get_amazon_api, item_lookup

amazon_api = get_amazon_api()

event = Event()
res = {}

parse.uses_netloc.append('postgres')
URL = os.environ['DATABASE_URL']
url = parse.urlparse(URL)

conn = pg.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)

CHANNEL_ACCESS_TOKEN = os.environ['CHANNEL_ACCESS_TOKEN']
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

def fetch(cur, res):
    res['fetch'] = cur.fetchmany(10)
    event.set(); event.clear()

def lookup(amazon_api, asins, res):
    res['lookup'] = item_lookup(amazon_api, asins)
    event.set(); event.clear()

def notify(user_id, product):
    text = '''商品「{}」の価格追跡条件が満たされました。
    https://amazon.co.jp/dp/{}
    '''.format(product['title'][:min(len(product['title']), 60)], product['asin'])
    text_message = TextSendMessage(text=text)
    confirm_message = TemplateSendMessage(
        alt_text='Confirm to continue tracking',
        template=ConfirmTemplate(
            text='価格追跡を継続しますか？',
            actions=[
                PostbackTemplateAction(
                    label='はい',
                    data='action=continue_tracking&asin={}'.format(product['asin'])
                ),
                PostbackTemplateAction(
                    label='いいえ',
                    data='action=end_tracking&asin={}'.format(product['asin'])
                )
            ]
        )
    )
    line_bot_api.push_message(user_id, [text_message, confirm_message])
    update_table(
        table='trackings',
        pkeys={'user_id': user_id, 'asin': product['asin']},
        notified=True
    )

def track():
    with conn.cursor(name='ssc') as ssc:
        ssc.execute('select asin from products')
        row = ssc.fetchmany(10)
        while len(row) != 0:
            asins = [r[0] for r in row]
            th1 = Thread(target=fetch, args=(ssc, res))
            th2 = Thread(target=lookup, args=(amazon_api, asins, res))
            th1.start(); th2.start()
            event.wait(); event.wait()
            product_dicts = res['lookup']
            for product in product_dicts:
                with conn.cursor() as csc:
                    csc.execute('select user_id, condition, tracking_price, notified from trackings where asin=%s', [product['asin']])
                    data = csc.fetchall()
                    for user_id, condition, tracking_price, notified in data:
                        lowestnewprice = product['lowestnewprice']
                        lowestusedprice = product['lowestusedprice']
                        lowestnewprice = int(lowestnewprice) if lowestnewprice is not None else 999999999
                        lowestusedprice = int(lowestusedprice) if lowestusedprice is not None else 999999999
                        minimum_price = lowestnewprice if condition == 'new' else min(lowestnewprice, lowestusedprice)
                        if minimum_price < tracking_price and not notified:
                            notify(user_id, product)
            row = res['fetch']

if __name__ == '__main__':
    track()
