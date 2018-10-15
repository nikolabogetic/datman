#!/bin/bash
PROJECT=$1
PYTHON=/opt/anaconda3/envs/datman-env/bin/python3.6

if [ $# -eq 0 ] ; then
    echo "Usage: ./ftp2xnat.sh <PROJECTID>"
    exit 1
fi

. /opt/anaconda3/envs/datman-env/etc/conda/activate.d/env_vars.sh &&
$PYTHON /usr/local/bin/datman/bin/dm_sftp.py -d $PROJECT &&
$PYTHON /usr/local/bin/datman/bin/write_manifest.py -d $PROJECT &&
$PYTHON /usr/local/bin/datman/bin/dm_link.py -d $PROJECT &&
$PYTHON /usr/local/bin/datman/bin/dm_xnat_upload.py -d $PROJECT &&
. /opt/anaconda3/envs/datman-env/etc/conda/deactivate.d/env_vars.sh &&
echo "###########################" &&
echo "##         DONE          ##"
echo "###########################"
