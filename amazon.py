#-*- coding: utf-8 -*-
import os
from functools import reduce
from urllib.error import HTTPError
from bottlenose import api
from bs4 import BeautifulSoup

AWS_ACCESS_KEY = os.environ['AWS_ACCESS_KEY']
AWS_SECRET_KEY = os.environ['AWS_SECRET_KEY']
AMAZON_ASSOCIATE_TAG = os.environ['AMAZON_ASSOCIATE_TAG']


def get_amazon_api():
    return api.Amazon(
        AWS_ACCESS_KEY,
        AWS_SECRET_KEY,
        AMAZON_ASSOCIATE_TAG,
        Region='JP'
    )

def api_request(amazon_api, operation='ItemSearch', *args, **kwargs):
    while True:
        try:
            return eval('amazon_api.{}(*args, **kwargs)'.format(operation))
        except HTTPError:
            continue
        except Exception:
            return '{}'

def scrape_xml(res_xml):
    soup = BeautifulSoup(res_xml, 'lxml')
    items = soup.findAll('item')
    res_dicts = []
    for item in items:
        try:
            res_dicts.append(
                {
                    'asin': item.find('asin').text,
                    'title': item.find('title').text,
                    'image_url': item.find('mediumimage').find('url').text
                }
            )
        except AttributeError:
            continue
        try:
            res_dicts[-1]['lowestnewprice'] = item.find('offersummary').find('lowestnewprice').find('amount').text
        except AttributeError as e:
            res_dicts[-1]['lowestnewprice'] = None
        try:
            res_dicts[-1]['lowestusedprice'] = item.find('offersummary').find('lowestusedprice').find('amount').text
        except AttributeError as e:
            res_dicts[-1]['lowestusedprice'] = None
        # TODO: res_dicts[-1]['last_update_time'] = datetime.now().tostring()
    return res_dicts

def item_search(amazon_api, keywords, ItemPage=1, ResponseGroup='Medium'):
    res_xml = api_request(
        amazon_api,
        operation='ItemSearch',
        SearchIndex='All',
        ItemPage=ItemPage,
        ResponseGroup=ResponseGroup,
        Keywords=keywords
    )
    return scrape_xml(res_xml)

def item_lookup(amazon_api, asins, ResponseGroup='Medium'):
    item_id = reduce(lambda asin1, asin2: asin1 + ',' + asin2, asins)
    res_xml = api_request(
        amazon_api,
        operation='ItemLookup',
        ItemId=item_id,
        ResponseGroup=ResponseGroup
    )
    return scrape_xml(res_xml)
