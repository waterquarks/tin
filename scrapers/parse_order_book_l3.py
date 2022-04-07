import sqlite3
import json


def main():
    db = sqlite3.connect('./order_book_l3.db')

    state = sqlite3.connect('./state.db')

    state.execute('drop table if exists orders')

    state.execute('drop table if exists snapshots')

    state.execute('create table if not exists orders (market text, side text, id text, price real, size real, account text, primary key (market, side, id) on conflict ignore)  without rowid')

    state.execute('create table if not exists snapshots (market text, "timestamp" text, side text, id text, price real, size real, account text, primary key (market, timestamp, side, id)) without rowid')

    state.set_trace_callback(print)

    for message in db.execute("""
        with
            subset as (
              select * from entries where local_timestamp
            ),
            snapshots as (
                select
                    json_extract(json(message), '$.market') as market,
                    json_extract(json(message), '$.type') as type,
                    json_extract(json(message), '$.timestamp') as "timestamp",
                    (
                        select
                            json_group_array(json_object(
                                'type', 'open',
                                'side', json_extract(json(value), '$.side'),
                                'id', json_extract(json(value), '$.orderId'),
                                'account', json_extract(json(value), '$.account'),
                                'price', json_extract(json(value), '$.price'),
                                'size', json_extract(json(value), '$.size')
                            )) as value
                        from (
                            select value from json_each(json(message), '$.bids')
                            union all
                            select value from json_each(json(message), '$.asks')
                        )
                    ) as orders
                from subset where type = 'l3snapshot'
            ),
            opens as (
                select
                    json_extract(json(message), '$.type') as type,
                    json_extract(json(message), '$.market') as market,
                    json_extract(json(message), '$.timestamp') as "timestamp",
                    json_extract(json(message), '$.slot') as slot,
                    json_object(
                        'side', json_extract(json(message), '$.side'),
                        'id', json_extract(json(message), '$.orderId'),
                        'account', json_extract(json(message), '$.account'),
                        'price', json_extract(json(message), '$.price'),
                        'size', json_extract(json(message), '$.size')
                    ) as "order"
                from subset where type = 'open'
            ),
            dones as (
                select
                    json_extract(json(message), '$.type') as type,
                    json_extract(json(message), '$.market') as market,
                    json_extract(json(message), '$.timestamp') as "timestamp",
                    json_extract(json(message), '$.slot') as slot,
                    json_object(
                        'side', json_extract(json(message), '$.side'),
                        'id', json_extract(json(message), '$.orderId'),
                        'account', json_extract(json(message), '$.account')
                    ) as "order"
                from subset where type = 'done'
            ),
            deltas as (
                select
                    market,
                    0 as is_snapshot,
                    timestamp,
                    json_group_array(json_insert(json("order"), '$.type', type)) as "orders"
                from (
                     select type, market, "timestamp", "order" from opens
                     union all
                     select type, market, "timestamp", "order" from dones
                )
                group by market, timestamp
            )
        select market, is_snapshot, timestamp, orders from deltas
        union all
        select market, 1 as is_snapshot, timestamp, orders from snapshots
        order by "timestamp";
    """):
        market, is_snapshot, timestamp, orders = message

        orders = json.loads(orders)

        if is_snapshot:
            state.execute('delete from orders where market = ?', [market])

        for order in orders:
            if order['type'] == 'open':
                state.execute('insert into orders values (?, ?, ?, ?, ?, ?)', [market, order['side'], order['id'], order['price'], order['size'], order['account']])

            if order['type'] == 'done':
                state.execute('delete from orders where market = ? and side = ? and id = ?', [market, order['side'], order['id']])

        state.execute('insert or ignore into snapshots select market, ? as timestamp, side, id, price, size, account from orders where market = ?', [timestamp, market])

    state.commit()


if __name__ == '__main__':
    main()