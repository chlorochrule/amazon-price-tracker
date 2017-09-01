#-*- coding: utf-8 -*-
import os
from functools import reduce
import psycopg2 as pg
from urllib import parse

from amazon import get_amazon_api, item_lookup

amazon_api = get_amazon_api()

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

def insert_table(table, **data):
    col_num = len(data.keys())
    if col_num == 0:
        return
    columns = reduce(lambda c1, c2: c1 + ', ' + c2, data.keys())
    form = '%s' + ', %s' * (col_num-1)
    with conn.cursor() as cur:
        cur.execute('insert into {table} ({columns}) values ({form});'.format(table=table, columns=columns, form=form), list(data.values()))
        conn.commit()
        if count_table(table='products', asin=data['asin']) == 0:
            product = item_lookup(amazon_api, asins=[data['asin']])[0]
            insert_table('products', **product)

def insert_table2(table, **data):
    col_num = len(data.keys())
    if col_num == 0:
        return
    columns = reduce(lambda c1, c2: c1 + ', ' + c2, data.keys())
    form = '%s' + ', %s' * (col_num-1)
    with conn.cursor() as cur:
        cur.execute('insert into {table} ({columns}) values ({form});'.format(table=table, columns=columns, form=form), list(data.values()))
        conn.commit()

def update_table(table, pkeys={}, **data):
    col_num = len(data.keys())
    if col_num == 0:
        return
    columns = ['{column}=%s'.format(column=column) for column in data.keys()]
    columns = reduce(lambda c1, c2: c1 + ', ' + c2, columns)
    wheres = ['{pkey}=%s'.format(pkey=pkey) for pkey in pkeys.keys()]
    wheres = reduce(lambda pk1, pk2: pk1 + ' and ' + pk2, wheres)
    with conn.cursor() as cur:
        sql = 'update {table} set {columns} where {wheres};'.format(table=table, columns=columns, wheres=wheres)
        payloads = list(data.values()) + list(pkeys.values())
        cur.execute(sql, payloads)
        conn.commit()

def fetch_table(table, columns, **wheres):
    res = []
    col_num = len(columns)
    if col_num != 0:
        columns = reduce(lambda c1, c2: c1 + ', ' + c2, columns)
        values = list(wheres.values())
        wheres = ['{key}=%s'.format(key=key) for key in wheres.keys()]
        wheres = reduce(lambda k1, k2: k1 + ' and ' + k2, wheres)
        with conn.cursor() as cur:
            cur.execute('select {columns} from {table} where {wheres};'.format(columns=columns, table=table, wheres=wheres), values)
            res = cur.fetchall()
            conn.commit()
    res.reverse()
    return res

def count_table(table, **wheres):
    values = list(wheres.values())
    wheres = ['{key}=%s'.format(key=key) for key in wheres.keys()]
    wheres = reduce(lambda k1, k2: k1 + ' and ' + k2, wheres)
    with conn.cursor() as cur:
        cur.execute('select count(*) from {table} where {wheres};'.format(table=table, wheres=wheres), values)
        res = cur.fetchone()[0]
        conn.commit()
        return res

def delete_table(user_id, asin):
    with conn.cursor() as cur:
        cur.execute('delete from trackings where user_id=%s and asin=%s', (user_id, asin))
        if count_table(table='trackings', asin=asin) == 0:
            cur.execute('delete from products where asin=%s;', [asin])
        conn.commit()

if __name__ == '__main__':
    pass
