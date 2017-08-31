#-*- coding: utf-8 -*-
import re
from json import loads, dumps
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    CarouselTemplate,
    CarouselColumn,
    PostbackTemplateAction,
    ButtonsTemplate,
    ConfirmTemplate
)

from amazon import get_amazon_api, item_search, item_lookup
from db import insert_table, update_table, fetch_table, count_table, delete_table

ASIN_PATTERN = '([0-9]{10})|(B[A-Z0-9]{9})'
URL_PATTERN = 'http[s]?://'

amazon_api = get_amazon_api()

class BaseHandler(object):
    """docstring for BaseHandler."""
    def __init__(self, line_bot_api):
        super(BaseHandler, self).__init__()
        self.line_bot_api = line_bot_api

    def handle(self, event):
        self._handle = self._dispatch_handler(event)
        self._handle(event)

    def _dispatch_handler(self, event):
        pass

    def _get_products(self, user_id, page=1, query=None):
        trackings = fetch_table(
            table='trackings',
            columns=['asin', 'condition', 'tracking_price'],
            user_id=user_id,
        )
        if len(trackings) <= (page - 1) * 4:
            return []
        else:
            trackings = trackings[(page-1)*4:min((page-1)*4+4, len(trackings))]
        product_dicts = []
        for asin, condition, tracking_price in trackings:
            product = {}
            product['asin'] = asin
            product['condition'] = condition
            product['tracking_price'] = tracking_price
            products = fetch_table(
                table='products',
                columns=['lowestnewprice', 'lowestusedprice', 'title', 'image_url'],
                asin=asin
            )[0]
            product['lowestnewprice'] = products[0]
            product['lowestusedprice'] = products[1]
            product['title'] = products[2]
            product['image_url'] = products[3]
            product_dicts.append(product)
        return product_dicts

    def _make_carousels(self, product_dicts, labels_actions, search_type=None):
        columns = [
            CarouselColumn(
                thumbnail_image_url=product['image_url'],
                title=product['title'][:min(30, len(product['title']))],
                text=product['text'],
                actions=[self._make_action(label=label, action=action,
                    asin=product['asin'], title=product['title'][:min(60, len(product['title']))]) for label, action in labels_actions]
            ) for product in product_dicts
        ]
        if search_type is not None:
            columns += [
                CarouselColumn(
                    thumbnail_image_url='https://i.imgur.com/OemfTPj.png',
                    title=' ',
                    text=' ',
                    actions=[
                        PostbackTemplateAction(
                            label='さらに表示',
                            data='action=more_info&search_type={}'.format(search_type)
                        )
                    ] + [
                        PostbackTemplateAction(
                            label=' ',
                            data='action=more_info&search_type={}'.format(search_type)
                        ) for _ in range(len(labels_actions)-1)
                    ]
                )
            ]
        return TemplateSendMessage(
            alt_text='Product Carousels',
            template=CarouselTemplate(
                columns=columns
            )
        )

    def _make_action(self, label, action, asin, title):
        return PostbackTemplateAction(
            label=label,
            data='action={action}&asin={asin}&title={title}'.format(
                action=action, asin=asin, title=title)
        )

    def _add_text(self, product_dicts, status):
        for product in product_dicts:
            product['text'] = self._make_text(product, status=status)
        return product_dicts

    def _make_text(self, product, status):
        if status == 'tracking':
            tracking_price = product['tracking_price']
            condition = None
            price = None
            if product['condition'] == 'new':
                condition = '新品のみ'
                price = product['lowestnewprice'] if product['lowestnewprice'] is not None else '価格がありません'
            else:
                condition = '中古&新品'
                if product['lowestnewprice'] is None and product['lowestusedprice'] is None:
                    price = '価格がありません'
                else:
                    if product['lowestnewprice'] is None:
                        product_condition = '中古'
                        price = product['lowestusedprice']
                    elif product['lowestusedprice'] is None:
                        product_condition = '新品'
                        price = product['lowestnewprice']
                    else:
                        used_is_lowest = product['lowestusedprice'] < product['lowestnewprice']
                        product_condition = '中古' if used_is_lowest else '新品'
                        price = product['lowestusedprice'] if used_is_lowest else product['lowestnewprice']
                    price = '{}({})'.format(price, product_condition)
            return '追跡する商品の状態：{}\n現在価格：￥{}\n追跡価格：￥{}'.format(condition, price, tracking_price)
        else:
            lowestnewprice = product['lowestnewprice'] if product['lowestnewprice'] is not None else '価格がありません'
            lowestusedprice = product['lowestusedprice'] if product['lowestusedprice'] is not None else '価格がありません'
            return '新品価格：￥{}\n中古価格：￥{}'.format(lowestnewprice, lowestusedprice)

    def _write_status(self, user_id, status):
        data = self._load_json(user_id)
        data['status'] = status
        self._save_json(user_id, data)

    def _write_products(self, user_id, product_dicts=None, displayed_products=None, tracking_product=None, page=None, query=None):
        data = self._load_json(user_id)
        data['products'] = product_dicts if product_dicts is not None else data['products']
        data['displayed_products'] = displayed_products if displayed_products is not None else data['displayed_products']
        data['tracking_product'] = tracking_product if tracking_product is not None else data['tracking_product']
        data['page'] = page if page is not None else data['page']
        data['query'] = query if query is not None else data['query']
        self._save_json(user_id, data)

    def _load_json(self, user_id):
        try:
            with open('staged/{user_id}.json'.format(user_id=user_id), 'r') as fh:
                return loads(fh.read())
        except FileNotFoundError as e:
            return {'status': 'init', 'products': [], 'page': 1, 'query': None, 'displayed_products': [], 'tracking_product': {}}

    def _save_json(self, user_id, data):
        with open('staged/{user_id}.json'.format(user_id=user_id), 'w') as fh:
            fh.write(dumps(data))

    def _choose_product(self, user_id, asin):
        data = self._load_json(user_id)
        displayed_products = data['displayed_products']
        tracking_product = None
        for product in displayed_products:
            if product['asin'] == asin:
                tracking_product = product
                break
        return tracking_product

    def _lookup_products(self, asins):
        return item_lookup(amazon_api, asins)

    def _search_products(self, query):
        product_dicts = item_search(amazon_api, keywords=query)
        if product_dicts is None:
            return [], -1
        else:
            page = 2
            while len(product_dicts) < 8:
                search_result = item_search(amazon_api, keywords=query, ItemPage=page)
                if search_result is None:
                    return product_dicts, -1
                else:
                    product_dicts += search_result
                page += 1
        return product_dicts, page

    def _send_message(self, event, message):
        self.line_bot_api.reply_message(
            event.reply_token,
            message
        )


class MessageHandler(BaseHandler):
    """docstring for MessageHandler."""
    def __init__(self, line_bot_api):
        super(MessageHandler, self).__init__(line_bot_api)

    def _dispatch_handler(self, event):
        text = event.message.text

        if text == '>処理を中断':
            return self._cancel_process
        elif text == '>追跡中商品一覧':
            return self._display_trackings_handler
        elif text == '>ヘルプ':
            return self._help_handler
        # elif text == '>追跡中の商品を検索':
        #     return self._start_searching_trackings_handler

        user_id = event.source.sender_id
        status = self._load_json(user_id=user_id)['status']

        if status == 'init':
            return self._init_handler
        # elif status == 'searching_trackings':
        #     return self._search_trackings_handler
        elif status == 'waiting_price_input':
            return self._price_inputed_handler

    def _cancel_process(self, event):
        message = TextSendMessage(text='処理を中断しました')
        self._send_message(event, message)
        user_id = event.source.sender_id
        data = {'status': 'init', 'products': [], 'page': 1, 'query': None, 'displayed_products': [], 'tracking_product': {}}
        self._save_json(user_id=user_id, data=data)

    def _display_trackings_handler(self, event, query=None):
        user_id = event.source.sender_id
        message = TextSendMessage(text='追跡中の商品はありません！')
        product_dicts = self._get_products(user_id, query=query)
        is_empty = len(product_dicts) == 0
        if not is_empty:
            labels_actions = [
                ('追跡価格の変更', 'modify_price'),
                ('商品状態の変更', 'modify_condition'),
                ('追跡の終了', 'end_tracking')
            ]
            product_dicts = self._add_text(product_dicts, status='tracking')
            message = self._make_carousels(product_dicts, labels_actions, search_type='tracking_search')
        self._send_message(event, message)
        if not is_empty:
            self._write_products(user_id, product_dicts=self._get_products(user_id, page=2, query=query),
                displayed_products=product_dicts, page=3, query=query)

    def _help_handler(self, event):
        text = '''これはAmazon.co.jpに登録されている商品の価格を追跡して指定された価格以下になったら通知してお知らせするLINEBOTです。

***使い方***
・追跡する商品を指定するには3通りの方法があります。
①このボットに検索するキーワードを送る
②AmazonのURLをこのボットに送る
③ASINをこのボットに送る

・追跡商品のコンディション
①新品のみを追跡
②新品と中古の両方を追跡

・価格入力
※アラビア数字半角で入力してください
良い例）4000、4000円
悪い例）4千円、４０００

・よくわからないとき
「処理を中断」ボタンを押してください
******

このボットはベータ版です。バグや要望、質問はTwitter @chlorochrule までお願いします。
よいAmazonライフを！
∈(´﹏﹏﹏｀)∋'''
        message = TextSendMessage(text=text)
        self._send_message(event, message)

    def _start_searching_trackings_handler(self, event):
        user_id = event.source.sender_id
        message = TextSendMessage(text='検索キーワードを入力してください')
        self._send_message(event, message)
        self._write_status(user_id=user_id, status='searching_trackings')

    def _init_handler(self, event):
        user_id = event.source.sender_id
        text = event.message.text
        labels_actions = [
            ('新品価格を追跡', 'track_new'),
            ('中古価格と新品価格を追跡', 'track_old')
        ]
        is_searching = False
        is_lookedup = False
        message = None
        page = None
        asin_mo = re.search('/' + ASIN_PATTERN, text)
        product_dicts = None
        thres = None
        if asin_mo:
            is_lookedup = True
            asin = asin_mo.group().replace('/', '')
            product_dicts = self._lookup_products(asins=[asin])
            product_dicts = self._add_text(product_dicts, status='not_tracking')
            message = self._make_carousels(product_dicts, labels_actions)
        elif re.search(URL_PATTERN, text):
            message = TextSendMessage(text='無効なURLです')
        else:
            product_dicts, page = self._search_products(query=text)
            thres = min(4, len(product_dicts))
            if thres == 0:
                message = TextSendMessage(text='該当なし><')
            else:
                is_searching = True
                product_dicts_added = self._add_text(product_dicts[:thres], status='not_tracking')
                message = self._make_carousels(product_dicts_added, labels_actions, search_type='product_search')
        self._send_message(event, message)
        if is_searching:
            while len(product_dicts[thres:]) < 4 and page != -1:
                search_result = item_search(amazon_api, keywords=text, ItemPage=page)
                if search_result is None:
                    page = -1
                    break
                else:
                    product_dicts += search_result
                page += 1
            self._write_products(user_id, product_dicts=product_dicts[thres:],
                displayed_products=product_dicts[:thres], query=text, page=page)
        if is_lookedup:
            self._write_products(user_id, displayed_products=product_dicts)

    # def _search_trackings_handler(self, event):
    #     text = eevnt.message.text
    #     self._display_trackings_handler(event, query=text)

    def _price_inputed_handler(self, event):
        text = event.message.text
        user_id = event.source.sender_id
        data = self._load_json(user_id)
        tracking_product = data['tracking_product']
        minimum_price = None
        if tracking_product['condition'] == 'new':
            minimum_price = tracking_product['lowestnewprice'] if tracking_product['lowestnewprice'] is not None else 999999999
        else:
            new_price = tracking_product['lowestnewprice'] if tracking_product['lowestnewprice'] is not None else 999999999
            used_price = tracking_product['lowestusedprice'] if tracking_product['lowestusedprice'] is not None else 999999999
            minimum_price = min(int(used_price), int(new_price))
        price = None
        minimum_price = int(minimum_price)
        price_mo = re.search('[0-9]+', text.replace(',', ''))
        is_tracked = False
        if not price_mo:
            message = TextSendMessage(text='数字を入力してください')
        elif 0 < int(price_mo.group()) < minimum_price:
            is_tracked = True
            price = int(price_mo.group())
            message = TextSendMessage(text='{}円で価格追跡を開始しました'.format(price))
            self._write_status(user_id=user_id, status='init')
        else:
            message = TextSendMessage(text='1~{}円の範囲で有効な価格を入力してください'.format(minimum_price-1))
        self._send_message(event, message)
        if is_tracked:
            cnt = count_table('trackings', user_id=user_id, asin=tracking_product['asin'])
            if cnt == 0:
                insert_table(
                    table='trackings',
                    user_id=user_id,
                    asin=tracking_product['asin'],
                    condition=tracking_product['condition'],
                    tracking_price=price,
                    notified=False
                )
            else:
                pkeys={'user_id': user_id, 'asin': tracking_product['asin']}
                update_table(
                    table='trackings',
                    pkeys=pkeys,
                    condition=tracking_product['condition'],
                    tracking_price=price
                )


class PostbackHandler(BaseHandler):
    """docstring for PostbackHandler."""
    def __init__(self, line_bot_api):
        super(PostbackHandler, self).__init__(line_bot_api)

    def _dispatch_handler(self, event):
        data = event.postback.data
        params = dict([param.split('=') for param in data.split('&')])
        action = params.get('action', None)
        asin = params.get('asin', None)
        search_type = params.get('search_type', None)
        title = params.get('title', None)
        if action == 'more_info':
            return lambda event: self._more_search_handler(event, search_type)
        elif action == 'modify_price':
            return lambda event: self._modify_price_handler(event, asin)
        elif action == 'modify_condition':
            return lambda event: self._modify_condition_handler(event, asin)
        elif action == 'end_tracking':
            return lambda event: self._end_tracking_handler(event, asin, title=title)
        elif action == 'continue_tracking':
            return lambda event: self._continue_tracking_handler(event, asin)
        elif action == 'not_change_price':
            return self._not_change_price_handler
        elif action == 'change_price':
            return lambda event: self._change_price_handler(event, asin)
        elif action == 'track_new':
            return lambda event: self._track_product_handler(event, asin, condition='new')
        else:
            return lambda event: self._track_product_handler(event, asin, condition='old')

    def _more_search_handler(self, event, search_type):
        user_id = event.source.sender_id
        data = self._load_json(user_id)
        product_dicts = data['products']
        thres = min(4, len(product_dicts))
        if thres == 0:
            message = TextSendMessage(text='該当なし>_<')
            self._send_message(event, message)
        else:
            product_dicts_rem = product_dicts[thres:]
            product_dicts = product_dicts[:thres]
            page = data['page']
            query = data['query']
            labels_actions = [
                ('新品価格を追跡', 'track_new'),
                ('中古価格と新品価格を追跡', 'track_old')
            ] if search_type == 'product_search' else [
                ('追跡価格の変更', 'modify_price'),
                ('商品状態の変更', 'modify_condition'),
                ('追跡の終了', 'end_tracking')
            ]
            status = 'tracking' if search_type == 'tracking_search' else 'not_tracking'
            product_dicts = self._add_text(product_dicts, status=status)
            message = self._make_carousels(product_dicts, labels_actions, search_type=search_type)
            self._send_message(event, message)
            if search_type == 'tracking_search':
                product_dicts = self._get_products(user_id, page=page)
                page += 1
            elif search_type == 'product_search':
                if len(product_dicts_rem) < 4:
                    product_dicts, page = self._search_products(query)
                    product_dicts = product_dicts_rem + product_dicts
                else:
                    product_dicts = product_dicts_rem
            self._write_products(user_id, product_dicts, page=page, query=query)

    def _modify_price_handler(self, event, asin):
        user_id = event.source.sender_id
        product = self._choose_product(user_id, asin)
        text = self._make_text(product, status='tracking')
        message = TextSendMessage(text='新しい追跡価格を入力してください\n\n現在の追跡情報\n------\n{}\n------'.format(text))
        self._send_message(event, message)
        self._write_status(user_id, status='waiting_price_input')
        self._write_products(user_id, tracking_product=product)

    def _modify_condition_handler(self, event, asin):
        message = TemplateSendMessage(
            alt_text='Modify Condition Button',
            template=ButtonsTemplate(
                title='追跡商品状態の変更',
                text='追跡する商品の状態を以下から選んでください',
                actions=[
                    PostbackTemplateAction(
                        label='新品のみ',
                        data='action=track_new&asin={}'.format(asin)
                    ),
                    PostbackTemplateAction(
                        label='中古&新品',
                        data='action=track_old&asin={}'.format(asin)
                    )
                ]
            )
        )
        self._send_message(event, message)

    def _end_tracking_handler(self, event, asin, title=None):
        user_id = event.source.sender_id
        if title is not None:
            message = TextSendMessage(text='商品「{}」の価格追跡を終了しました'.format(title))
        else:
            message = TextSendMessage(text='商品の価格追跡を終了しました')
        self._send_message(event, message)
        self._end_track(user_id, asin)

    def _continue_tracking_handler(self, event, asin=None):
        user_id = event.source.sender_id
        message = TemplateSendMessage(
            alt_text='Confirm to change tracking price',
            template=ConfirmTemplate(
                text='追跡価格を変更しますか？',
                actions=[
                    PostbackTemplateAction(
                        label='はい',
                        data='action=change_price&asin={}'.format(asin)
                    ),
                    PostbackTemplateAction(
                        label='いいえ',
                        data='action=not_change_price'
                    )
                ]
            )
        )
        self._send_message(event, message)
        update_table(
            table='trackings',
            pkeys={'user_id': user_id, 'asin': asin},
            notified=False
        )

    def _not_change_price_handler(self, event):
        message = TextSendMessage(text='現在の追跡条件で価格追跡を継続します')
        self._send_message(event, message)

    def _change_price_handler(self, event, asin):
        user_id = event.source.sender_id
        message = TextSendMessage(text='追跡したい価格を入力してください')
        self._send_message(event, message)
        product = self._lookup_products(asins=[asin])[0]
        condition = fetch_table(
            table='trackings',
            columns=['condition'],
            user_id=user_id,
            asin=asin
        )[0][0]
        product['condition'] = condition
        self._write_products(user_id, tracking_product=product)
        self._write_status(user_id, status='waiting_price_input')

    def _track_product_handler(self, event, asin, condition):
        user_id = event.source.sender_id
        product = self._choose_product(user_id, asin)
        thres = min(20, len(product['title']))
        title = product['title'][:thres]
        if thres == 20:
            title += '...'
        message = TextSendMessage(text='商品「{}」の価格を追跡します。追跡したい価格を入力してください。'.format(title))
        self._send_message(event, message)
        product['condition'] = condition
        self._write_products(user_id, tracking_product=product)
        self._write_status(user_id, status='waiting_price_input')

    def _end_track(self, user_id, asin):
        delete_table(user_id=user_id, asin=asin)
