# gri

* コンテナ内 名前解決テスト
    ```
    $ perl -e 'print inet_ntoa(scalar gethostbyname("ttj1gw1.tun.y2e.org")) . "\n"' -MSocket
    ```

* sysdb から古いホストを削除する
    ```
    $ sed -i '/_host:ibr1wstep1\.tail5b1c5\.ts\.net/d' /usr/local/gri/gra/.sysdb/sysdb.txt
    ```
