# LAN9662 TSN Switch 빠른 테스트 가이드

## 1. 기본 네트워크 설정

### 1.1 인터페이스 확인
```bash
# 로그인 후 실행
ip link show
cat /proc/net/dev
lspci -v
```

### 1.2 기본 IP 설정
```bash
# 메인 인터페이스 설정
ip addr add 192.168.1.100/24 dev eth0
ip link set eth0 up

# TSN 포트 설정 (예시)
ip addr add 192.168.100.1/24 dev sw0p0
ip link set sw0p0 up
```

## 2. TSN 기능 테스트

### 2.1 PTP 시간 동기화 테스트
```bash
# PTP4L 실행 (IEEE 802.1AS)
ptp4l -i eth0 -s -m &

# PTP 상태 확인
pmc -u -b 0 'GET CURRENT_DATA_SET'
```

### 2.2 FRER 기능 활성화
```bash
# FRER 스트림 설정
echo "stream_id=100,sgf=1,srf=1" > /sys/class/net/eth0/frer_config

# 복제 경로 설정
echo "primary_port=0,secondary_port=1" > /sys/class/net/eth0/frer_path
```

## 3. 기본 연결 테스트

### 3.1 외부 장비와 ping 테스트
```bash
# 외부 PC/ECU와 연결 테스트
ping -c 10 192.168.1.200

# 지연시간 정밀 측정
ping -c 100 -i 0.01 192.168.1.200
```

### 3.2 네트워크 성능 측정
```bash
# iperf3 서버 실행
iperf3 -s &

# 처리량 테스트 (클라이언트에서)
iperf3 -c 192.168.1.100 -t 30
```

## 4. TSN 스위치 상태 확인

### 4.1 포트 상태 확인
```bash
# 스위치 포트 통계
cat /sys/class/net/*/statistics/rx_packets
cat /sys/class/net/*/statistics/tx_packets

# 링크 상태
ethtool eth0
```

### 4.2 FRER 통계 확인
```bash
# FRER 동작 통계
cat /proc/net/frer_stats
cat /sys/class/net/eth0/frer/eliminated_duplicates
```

## 5. 문제 해결

### 5.1 일반적인 문제
- **SSH 실패**: dropbear 설정 확인
- **PTP 동기화 실패**: 네트워크 케이블 및 설정 확인
- **FRER 동작 안됨**: 커널 모듈 로딩 상태 확인

### 5.2 디버그 명령어
```bash
# 커널 메시지 확인
dmesg | grep -i "lan966x\|frer\|tsn"

# 프로세스 확인
ps aux | grep ptp
ps aux | grep frer

# 네트워크 설정 확인
ip route show
ip addr show
```

## 6. 성능 벤치마크 실행

### 6.1 우리 테스트 스위트 업로드
```bash
# SCP로 파일 전송 (Windows에서)
scp software/test_suite.py root@192.168.1.100:/root/
scp software/frer_implementation.c root@192.168.1.100:/root/

# 또는 USB/wget 사용
wget https://raw.githubusercontent.com/hwkim3330/tsn-frer-automotive-redundancy/master/software/test_suite.py
```

### 6.2 테스트 실행
```bash
# Python 테스트 스위트 실행
python3 test_suite.py --local-ip 192.168.1.100 --remote-ip 192.168.1.200 --test all
```

이제 실제 하드웨어에서 우리 연구 내용을 검증할 수 있습니다! 🚀