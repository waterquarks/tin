import sqlite3
import json
import psycopg2
import psycopg2.extras
from pathlib import Path

def main(hour):
    db = sqlite3.connect(f"{str(Path(__file__).parent / 'spreads_midweek_program.db')}")

    db.execute('pragma journal_mode=WAL')

    db.execute('pragma synchronous=1')

    db.execute('create table if not exists competitors (account text, market text, target_depth integer, primary key (account, market, target_depth)) without rowid;')

    db.execute("""
        insert or replace into competitors values
            ('4rm5QCgFPm4d37MCawNypngV4qPWv4D5tw57KE2qUcLE', 'AVAX-PERP', 25000),
            ('4rm5QCgFPm4d37MCawNypngV4qPWv4D5tw57KE2qUcLE', 'BTC-PERP', 25000),
            ('4rm5QCgFPm4d37MCawNypngV4qPWv4D5tw57KE2qUcLE', 'ETH-PERP', 25000),
            ('4rm5QCgFPm4d37MCawNypngV4qPWv4D5tw57KE2qUcLE', 'SOL-PERP', 25000)
    """)

    db.execute('create table if not exists target_spreads (market text, target_depth integer, target_spread real, primary key (market, target_depth)) without rowid;')

    db.execute("""
        insert or replace into target_spreads values
            ('BTC-PERP', 12500, 0.2),
            ('ETH-PERP', 12500, 0.2),
            ('SOL-PERP', 12500, 0.3),
            ('AVAX-PERP', 12500, 0.3),
            ('ADA-PERP', 12500, 0.75),
            ('BNB-PERP', 12500, 0.75),
            ('FTT-PERP', 12500, 0.75),
            ('MNGO-PERP', 12500, 0.75),
            ('SRM-PERP', 12500, 0.75),
            ('RAY-PERP', 12500, 0.75),
            ('BTC-PERP', 25000, 0.2),
            ('ETH-PERP', 25000, 0.2),
            ('SOL-PERP', 25000, 0.3),
            ('AVAX-PERP', 25000, 0.3),
            ('ADA-PERP', 25000, 0.75),
            ('BNB-PERP', 25000, 0.75),
            ('FTT-PERP', 25000, 0.75),
            ('MNGO-PERP', 25000, 0.75),
            ('SRM-PERP', 25000, 0.75),
            ('RAY-PERP', 25000, 0.75),
            ('BTC-PERP', 50000, 0.5),
            ('ETH-PERP', 50000, 0.5),
            ('SOL-PERP', 50000, 0.5),
            ('AVAX-PERP', 50000, 0.5),
            ('ADA-PERP', 50000, 0.75),
            ('BNB-PERP', 50000, 0.75),
            ('FTT-PERP', 50000, 0.75),
            ('MNGO-PERP', 50000, 0.75),
            ('SRM-PERP', 50000, 0.75),
            ('RAY-PERP', 50000, 0.75)
    """)

    db.execute('create table if not exists target_uptimes (target_depth integer, target_uptime real, primary key (target_depth)) without rowid;')

    db.execute("""
        insert or replace into target_uptimes values
            (12500, 0.825),
            (25000, 0.80),
            (50000, 0.80)
    """)

    [tranches] = db.execute("""
        with
            tranches as (
                select
                    market,
                    json_group_array (
                        json_array (
                            account,
                            target_depth,
                            target_spread
                        )
                    ) as competitors
                from competitors
                inner join target_spreads using (market, target_depth)
                group by market
            )
        select json_group_object(market, competitors) as value from tranches;
    """).fetchone()

    tranches = json.loads(tranches)

    db.execute("""
        create table if not exists spreads (
            market text,
            account text,
            target_depth integer,
            target_spread real,
            bids real,
            asks real,
            spread real,
            has_target_spread integer,
            has_any_spread integer,
            slot integer,
            "timestamp" text,
            primary key (market, account, target_depth, "timestamp")
        ) without rowid
    """)

    db.execute("""
        create table if not exists orders (
            market text,
            side text,
            order_id text,
            account text,
            price real,
            size real,
            primary key (market, side, order_id)
        ) without rowid
    """)

    conn = psycopg2.connect('dbname=mangolorians')

    cur = conn.cursor('cur')

    query = """
        with
             entries as (
                 select content ->> 'market' as market
                      , content ->> 'type' = 'l3snapshot' as is_snapshot
                      , content
                      , (content ->> 'slot')::integer as slot
                      , (content ->> 'timestamp')::timestamptz at time zone 'utc' as "timestamp"
                      , local_timestamp
                 from mango_bowl.level3
                 where date_trunc('hour', local_timestamp at time zone 'utc') = %s
                   and content ->> 'type' in ('l3snapshot', 'open', 'done')
             ),
             anchors as (
                select
                    market, min(local_timestamp) as local_timestamp
                from entries
                where is_snapshot
                group by market, is_snapshot
             ),
             snapshots as (
                 select market, is_snapshot, content, slot, timestamp, local_timestamp
                 from anchors inner join entries using (market, local_timestamp)
             ),
             deltas as (
                select entries.market
                     , entries.is_snapshot
                     , entries.content
                     , entries.slot
                     , entries.timestamp
                     , entries.local_timestamp
                from snapshots inner join entries on entries.market = snapshots.market and entries.local_timestamp > snapshots.local_timestamp
             ),
             batch as (
                select market
                     , is_snapshot
                     , content
                     , slot
                     , timestamp
                     , local_timestamp
                from snapshots
                union all
                select market
                     , is_snapshot
                     , content
                     , slot
                     , timestamp
                     , local_timestamp
                from deltas
             ),
             collapsable as (
                select market
                     , is_snapshot
                     , case
                         when content->>'type' = 'l3snapshot' then
                            (
                                select
                                    json_agg(
                                        json_build_array(
                                            value->>'account',
                                            value->>'side',
                                            value->>'orderId',
                                            (value->>'price')::float,
                                            (value->>'size')::float
                                        )
                                    )
                                from (
                                    select * from jsonb_array_elements(content->'bids')
                                    union all
                                    select * from jsonb_array_elements(content->'asks')
                                ) as orders
                            )
                        when content->>'type' = 'open' then
                            json_build_array(
                                json_build_array(
                                    content->>'account',
                                    content->>'side',
                                    content->>'orderId',
                                    (content->>'price')::float,
                                    (content->>'size')::float
                                )
                            )
                        when content->>'type' = 'done' then
                            json_build_array(
                                json_build_array(
                                    content->>'account',
                                    content->>'side',
                                    content->>'orderId',
                                    0,
                                    0
                                )
                            )
                     end as orders
                     , slot
                     , timestamp
                     , local_timestamp
                from batch order by market, local_timestamp
             ),
             collapsed as (
                select market
                     , is_snapshot
                     , value->>0 as account
                     , value->>1 as side
                     , value->>2 as order_id
                     , (value->>3)::float as price
                     , (value->>4)::float as size
                     , slot
                     , timestamp
                     , local_timestamp
                from collapsable, json_array_elements(orders)
                order by market, local_timestamp
             )
        select market
             , is_snapshot
             , json_build_object(
                'bids', coalesce(json_agg(json_build_array(account, order_id, price, size)) filter ( where side = 'buy' ), json_build_array()),
                'asks', coalesce(json_agg(json_build_array(account, order_id, price, size)) filter ( where side = 'sell' ), json_build_array())
               ) as orders
             , slot
             , "timestamp"
        from collapsed
        group by market, is_snapshot, slot, "timestamp"
        order by market, "timestamp";
    """

    cur.execute(query, [hour])

    for market, is_snapshot, orders, slot, timestamp in cur:
        print(market, slot, timestamp)

        if is_snapshot:
            db.execute('delete from orders where market = ?', [market])

        for side in {'bids', 'asks'}:
            for account, order_id, price, size in orders[side]:
                if price == 0:
                    db.execute('delete from orders where market = ? and side = ? and order_id = ?', [market, side, order_id])
                else:
                    db.execute('insert or replace into orders values (?, ?, ?, ?, ?, ?)', [market, side, order_id, account, price, size])
        else:
            if market not in tranches.keys():
                continue

            for [account, target_depth, target_spread] in tranches[market]:
                db.execute("""
                    insert or replace into spreads
                    with
                        orders as (
                            select
                                side,
                                price,
                                sum(size) as size,
                                price * sum(size) as volume,
                                sum(price * sum(size)) over (partition by side order by case when side = 'bids' then - price when side = 'asks' then price end) as cumulative_volume
                            from main.orders
                            where market = :market and account = :account
                            group by side, price
                            order by side, case when side = 'bids' then - price when side = 'asks' then price end
                        ),
                        fills as (
                            select
                                side, price, fill, sum(fill) over (partition by side order by case when side = 'bids' then - price when side = 'asks' then price end) as cumulative_fill
                            from (
                                select
                                    side,
                                    price,
                                    case when cumulative_volume < :target_depth then volume else coalesce(lag(remainder) over (partition by side), case when volume < :target_depth then volume else :target_depth end) end as fill
                                from (select *, :target_depth - cumulative_volume as remainder from orders) as alpha
                            ) as beta
                            where fill > 0
                        ),
                        weighted_average_quotes as (
                            select
                                case when sum(case when side = 'bids' then fill end) = :target_depth then sum(case when side = 'bids' then price * fill end) / :target_depth end as weighted_average_bid,
                                case when sum(case when side = 'asks' then fill end) = :target_depth then sum(case when side = 'asks' then price * fill end) / :target_depth end as weighted_average_ask,
                                coalesce(sum(case when side = 'bids' then fill end), 0) > 0 and coalesce(sum(case when side = 'asks' then fill end), 0) > 0 as has_any_spread
                            from fills
                        ),
                        spreads as (
                            select
                                weighted_average_bid,
                                weighted_average_ask,
                                ((weighted_average_ask - weighted_average_bid) / weighted_average_ask) * 1e2 as spread,
                                has_any_spread
                            from weighted_average_quotes
                        ),
                        depth as (
                            select
                                coalesce(sum(price * size) filter ( where side = 'bids' ), 0) as bids,
                                coalesce(sum(price * size) filter ( where side = 'asks' ), 0) as asks
                            from orders
                        )
                    select
                        :market as market,
                        :account as account,
                        :target_depth as target_depth,
                        :target_spread as target_spread,
                        bids,
                        asks,
                        spread,
                        spread <= :target_spread as has_target_spread,
                        has_any_spread,
                        :slot as slot,
                        :timestamp as "timestamp"
                    from spreads, depth
                """, {
                    'account': account,
                    'market': market,
                    'target_depth': target_depth,
                    'target_spread': target_spread,
                    'slot': slot,
                    'timestamp': timestamp
                })

    db.commit()


if __name__ == '__main__':
    conn = psycopg2.connect('dbname=mangolorians')

    cur = conn.cursor()

    cur.execute("select generate_series at time zone 'utc' from generate_series('2022-05-09 12:00:00'::timestamptz at time zone 'utc', current_timestamp, interval '1 hour');")

    for hour in cur:
        main(hour)