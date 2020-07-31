#!/bin/bash

DRIVE=/dev/sr0
RIP_PATH=/psx
TEMP_STOR=/tmp/wav

mkdir -p ${TEMP_STOR}

while sleep 15
do
    udevadm info --query=property ${DRIVE} | grep ID_CDROM_MEDIA=1
    while [ $? -ne 0 ]
    do
	sleep 15
	echo -n "."
	udevadm info --query=property ${DRIVE} | grep ID_CDROM_MEDIA=1
    done
    sleep 15

DISCDATA=$(udevadm info --query=property ${DRIVE})

APP_ID=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_APPLICATION_ID= | cut -d = -f2)
if [ ${APP_ID} != "PLAYSTATION" ]; then
    echo "App ID not PLAYSTATION: ${APP_ID}"
    eject /dev/sr1
    continue
fi

FS_UUID=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_UUID= | cut -d = -f2)
if [ -z "${FS_UUID}" ]; then
    echo "No UUID Found!"
    FS_UUID=$(date +%s)
fi

# Now grab fun tags if possible

PUB_ID=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_PUBLISHER_ID= | cut -d = -f2)
if [ -z "${PUB_ID}" ]; then
    PUB_ID="Unk_Publisher"
fi

FS_LABEL=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_LABEL= | cut -d = -f2)
if [ -z "${FS_LABEL}" ]; then
    FS_LABEL="${FS_UUID}"
fi

AUDIO_COUNT=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_CDROM_MEDIA_TRACK_COUNT_AUDIO= | cut -d = -f2)

FULL_PATH="${RIP_PATH}/${APP_ID}/${PUB_ID}/${FS_LABEL}"
mkdir -p ${FULL_PATH}
touch ${FULL_PATH}/${FS_UUID}

echo "Found ${PUB_ID} ${FS_LABEL}"

# Grab both with subchannel data and without
if [ ! -f "${FULL_PATH}/${FS_LABEL}_ns.bin" ]; then
    cdrdao read-cd --read-raw --datafile ${FULL_PATH}/${FS_LABEL}_ns.bin --device ${DRIVE} --driver generic-mmc-raw ${FULL_PATH}/${FS_LABEL}_ns.toc
fi

if [ ! -f "${FULL_PATH}/${FS_LABEL}.bin" ]; then
    cdrdao read-cd --read-raw --read-subchan rw_raw --datafile ${FULL_PATH}/${FS_LABEL}.bin --device ${DRIVE} --driver generic-mmc-raw ${FULL_PATH}/${FS_LABEL}.toc
fi

toc2cue ${FULL_PATH}/${FS_LABEL}_ns.toc ${FULL_PATH}/${FS_LABEL}_ns.cue
toc2cue ${FULL_PATH}/${FS_LABEL}.toc ${FULL_PATH}/${FS_LABEL}.cue

if [ -n "${AUDIO_COUNT}" ]; then
    MYCWD=${pwd}
    cd ${TEMP_STOR}
    rm -f *
    cdparanoia -Bwd ${DRIVE}
    for WAV in $(ls -1 *.wav)
    do
	SHORT=$(basename ${WAV} .cdda.wav)
	lame -k -h -m j -v -V 4 ${WAV} ${FULL_PATH}/${SHORT}.mp3
	rm -f ${WAV}
    done
    cd ${MYCWD}
fi
sleep 5
echo "Finished ${PUB_ID} ${FS_LABEL}"
eject ${DRIVE}
sleep 5
done
