#!/bin/sh

DIR=key/
TMP=$DIR/authorized_keys
TARGET=/home/console/.ssh/authorized_keys

truncate -s 0 $TMP
for f in `ls $DIR/*.pub`
do
    cat $f >> $TMP
done
cp $TMP $TARGET
