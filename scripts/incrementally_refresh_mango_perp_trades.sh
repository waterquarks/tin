#!/bin/bash

psql postgres://waterquarks:IgWTTJNAY3JEkcy9@replica-event-history-maximilian-5ee2.a.timescaledb.io:25548/event-history << EOF | psql -d mangolorians -c "copy trades from stdin csv header"
copy (
    with
        perp_markets(address, name) as (
            values
            ('4nfmQP3KmUqEJ6qJLsS3offKgE96YUB4Rp7UQvm2Fbi9', 'MNGO-PERP'),
            ('DtEcjPLyD4YtTBB4q8xwFZ9q49W89xZCZtJyrGebi5t8', 'BTC-PERP'),
            ('DVXWg6mfwFvHQbGyaHke4h3LE9pSkgbooDSDgA4JBC8d', 'ETH-PERP'),
            ('2TgaaVoHgnSeEtXvWTx13zQeTf4hYWAMEiMQdcG6EwHi', 'SOL-PERP'),
            ('4GkJj2znAr2pE2PBbak66E12zjCs2jkmeafiJwDVM9Au', 'SRM-PERP'),
            ('6WGoQr5mJAEpYCdX6qjju2vEnJuD7e8ZeYes7X7Shi7E', 'RAY-PERP'),
            ('AhgEayEGNw46ALHuC5ASsKyfsJzAm5JY8DWqpGMQhcGC', 'FTT-PERP'),
            ('Bh9UENAncoTEwE7NDim8CdeM1GPvw6xAT4Sih2rKVmWB', 'ADA-PERP'),
            ('CqxX2QupYiYafBSbA519j4vRVxxecidbh2zwX66Lmqem', 'BNB-PERP'),
            ('EAC7jtzsoQwCbXj1M3DapWrNLnc3MBwXAarvWDPr2ZV9', 'AVAX-PERP'),
            ('BCJrpvsB2BJtqiDgKVC4N6gyX1y24Jz96C6wMraYmXss', 'LUNA-PERP')
        )
    select "seqNum" as id
         , perp_markets.name as market
         , price
         , quantity
         , maker
         , "makerOrderId" as maker_order_id
         , "makerClientOrderId" as maker_client_order_isd
         , taker
         , "takerOrderId" as taker_order_id
         , "takerClientOrderId" as taker_client_order_id
         , "makerFee" as maker_fee
         , "takerFee" as taker_fee
         , "takerSide" as taker_side
         , "loadTimestamp" as "timestamp"
    from perp_event
    inner join perp_markets using (address)
    where "loadTimestamp" >= date_trunc('day', current_timestamp) - interval '1 day'
      and "loadTimestamp" < date_trunc('day', current_timestamp)
    order by market, "seqNum"
) to stdout csv header;
EOF