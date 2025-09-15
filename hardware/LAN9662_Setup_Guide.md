# Microchip LAN9662 TSN Switch 설정 가이드

## 1. 하드웨어 개요

### 1.1 LAN9662 사양
- **CPU**: ARM Cortex-A7 듀얼코어 600MHz
- **스위치 엔진**: 8포트 기가비트 이더넷
- **TSN 기능**: IEEE 802.1AS, 802.1Qbv, 802.1CB(FRER) 지원
- **메모리**: 512MB DDR3 RAM, 64MB NAND Flash
- **전원**: 12V DC, 최대 15W

### 1.2 핀아웃 및 연결
```
Port 0-7: 기가비트 이더넷 포트
UART: 디버그 콘솔 (115200 baud)
GPIO: 사용자 정의 I/O
SPI: 외부 디바이스 연결
```

## 2. 초기 설정

### 2.1 부트로더 설정
```bash
# U-Boot 환경변수 설정
setenv ipaddr 192.168.1.100
setenv serverip 192.168.1.1
setenv bootcmd 'dhcp; bootm'
saveenv
```

### 2.2 Linux 이미지 플래시
```bash
# TFTP를 통한 커널 업로드
tftp 0x40000000 uImage
nand erase 0x200000 0x800000
nand write 0x40000000 0x200000 0x800000
```

## 3. TSN 기능 설정

### 3.1 시간 동기화 (gPTP)
```bash
# PTP 데몬 설정
cat > /etc/ptp4l.conf << EOF
[global]
dataset_comparison   gmCapable
priority1            248
priority2            248
domainNumber         0
clockClass           248
clockAccuracy        0xFE
offsetScaledLogVariance 0xFFFF
free_running         0
freq_est_interval    1
dscp_event           0
dscp_general         0
network_transport    L2
delay_mechanism      E2E

[eth0]
masterOnly           0
delay_filter         moving_median
delay_filter_length  10
egressLatency        0
ingressLatency       0
EOF

# PTP 시작
ptp4l -f /etc/ptp4l.conf -i eth0 -s -m &
```

### 3.2 트래픽 셰이핑 (Qbv)
```bash
# 시간 인식 셰이퍼 설정
tc qdisc add dev eth0 root mqprio num_tc 8 \
   map 0 1 2 3 4 5 6 7 \
   queues 1@0 1@1 1@2 1@3 1@4 1@5 1@6 1@7 \
   hw 1

# 게이트 제어 목록 설정
tc qdisc add dev eth0 parent mqprio taprio \
   num_tc 8 \
   map 0 1 2 3 4 5 6 7 \
   queues 1@0 1@1 1@2 1@3 1@4 1@5 1@6 1@7 \
   base-time 0 \
   sched-entry S 01 250000 \
   sched-entry S 02 250000 \
   sched-entry S 04 250000 \
   sched-entry S 08 250000 \
   clockid CLOCK_TAI
```

### 3.3 FRER 설정
```bash
# FRER 스트림 설정
echo "100,1,1" > /sys/class/net/eth0/frer/stream_table
echo "101,1,1" > /sys/class/net/eth0/frer/stream_table

# Sequence Generation Function 설정
echo "enable" > /sys/class/net/eth0/frer/sgf/stream_100
echo "2" > /sys/class/net/eth0/frer/sgf/stream_100/path_count

# Sequence Recovery Function 설정  
echo "enable" > /sys/class/net/eth0/frer/srf/stream_100
echo "64" > /sys/class/net/eth0/frer/srf/stream_100/history_length
echo "1000" > /sys/class/net/eth0/frer/srf/stream_100/recovery_timeout
```

## 4. 성능 모니터링

### 4.1 통계 확인
```bash
# 포트별 통계
cat /sys/class/net/eth0/statistics/rx_packets
cat /sys/class/net/eth0/statistics/tx_packets

# FRER 통계
cat /sys/class/net/eth0/frer/stats/duplicates_eliminated
cat /sys/class/net/eth0/frer/stats/sequence_errors
```

### 4.2 실시간 모니터링
```bash
# 지연시간 모니터링
while true; do
    ping -c 1 192.168.1.200 | grep time=
    sleep 0.1
done

# 트래픽 모니터링
tcpdump -i eth0 -nn ether[12:2] = 0x891D
```