#!/bin/bash
PROJECT=$1

if [ $# -eq 0 ] ; then
    echo "Usage: ./ftp2xnat.sh <PROJECTID>"
    exit 1
fi

conda activate datman-env &&
python dm_sftp.py -d $PROJECT &&
python write_manifest.py -d $PROJECT &&
python dm_link.py -d $PROJECT &&
python dm_xnat_upload.py -d $PROJECT &&
conda deactivate &&
echo "###########################"
echo "##         DONE          ##"
echo "###########################"

