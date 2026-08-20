#!/bin/bash
set -e
SP="$(cd "$(dirname "$0")" && pwd)"
cd "$SP"
ffmpeg -y -v error \
  -i t1-olaf-zaehlt.mp4 -i t2-olaf-beratung.mp4 \
  -i t3-babs-scan.mp4 -i t4-babs-haken.mp4 \
  -loop 1 -t 4 -i endcard.png -f lavfi -t 4 -i anullsrc=r=48000:cl=stereo \
  -filter_complex "\
    [0:v]scale=720:1280,setsar=1,fps=24[v0];\
    [1:v]scale=720:1280,setsar=1,fps=24[v1];\
    [2:v]scale=720:1280,setsar=1,fps=24[v2];\
    [3:v]scale=720:1280,setsar=1,fps=24[v3];\
    [4:v]scale=720:1280,setsar=1,fps=24,format=yuv420p[v4];\
    [v0][0:a][v1][1:a][v2][2:a][v3][3:a][v4][5:a]concat=n=5:v=1:a=1[vc][ac];\
    [vc]subtitles=spot.srt:force_style='FontName=Helvetica,FontSize=13,PrimaryColour=&HFFFFFF&,OutlineColour=&H50000000&,BorderStyle=1,Outline=1,Shadow=0,MarginV=36'[vs]" \
  -map "[vs]" -map "[ac]" -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 160k \
  spot-olaf-rechnet-ab.mp4
echo "SPOT FERTIG: $(du -h spot-olaf-rechnet-ab.mp4 | cut -f1)"
