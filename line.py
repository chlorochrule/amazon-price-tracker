#-*- coding: utf-8 -*-
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    CarouselTemplate,
    CarouselColumn,
    PostbackTemplateAction
)

from amazon import get_amazon_api, item_search, item_lookup

amazon_api = get_amazon_api()

def get_response_message(action, *args, **kwargs):
    if action == 'input_price_ok':
        return TextSendMessage(text='トラッキングを開始したよ。商品価格が指定した値段を下回ったら教えるね。')
    elif action == 'input_price_range_ng':
        return TextSendMessage(text='無効な範囲だよ。0~{}の間の数字で入力してね。'.format(kwargs['price']))
    elif action == 'input_price_style_ng':
        return TextSendMessage(text='無効な入力だよ。数字を入力してね。')
    elif action == 'sent_url_ok':
        product = item_lookup(amazon_api, asins=[kwargs['asin']])[0]
        return TemplateSendMessage(
            alt_text='Amazon Product',
            template=CarouselTemplate(
                columns=[
                    CarouselColumn(
                        thumbnail_image_url=product['image_url'],
                        title=product['title'][:min(40, len(product['title']))],
                        text='新品：{} 円\n中古：{} 円'.format(product['lowestnewprice'], product['lowestusedprice']),
                        actions=[
                            PostbackTemplateAction(
                                label='新品のみ追跡',
                                text=product['title'] + '\n' + 'Track Type: NEW only',
                                data='tracktype=newonly&asin={}&price={}'.format(product['asin'], product['lowestnewprice'])
                            ),
                            PostbackTemplateAction(
                                label='新品と中古を両方追跡',
                                text=product['title'] + '\n' + 'Track Type: NEW and USED',
                                data='tracktype=newandused&asin={}&price={}'.format(product['asin'], product['lowestusedprice'])
                            )
                        ]
                    )
                ]
            )
        )
    elif action == 'sent_url_ng':
        return TextSendMessage(text='無効なURLだよ。正しい商品のURLを入力してね。')
    elif action == 'search_product':
        res_dicts = item_search(amazon_api, kwargs['query'])
        return TemplateSendMessage(
            alt_text='Amazon Product',
            template=CarouselTemplate(
                columns=[
                    CarouselColumn(
                        thumbnail_image_url=product['image_url'],
                        title=product['title'][:min(40, len(product['title']))],
                        text='新品：{} 円\n中古：{} 円'.format(product['lowestnewprice'], product['lowestusedprice']),
                        actions=[
                            PostbackTemplateAction(
                                label='新品のみ追跡',
                                text=product['title'] + '\n' + 'Track Type: NEW only',
                                data='tracktype=newonly&asin={}&price={}'.format(product['asin'], product['lowestnewprice'])
                            ),
                            PostbackTemplateAction(
                                label='新品と中古を両方追跡',
                                text=product['title'] + '\n' + 'Track Type: NEW and USED',
                                data='tracktype=newandused&asin={}&price={}'.format(product['asin'], product['lowestusedprice'])
                            )
                        ]
                    ) for product in res_dicts[:min(5, len(res_dicts))]
                ]
            )
        )
    else:
        return TextSendMessage(text='わけがわからないよ！')
