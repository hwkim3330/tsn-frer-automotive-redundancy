# LAN9662 포트 활성화 및 FRER 테스트 가이드

## 1. 현재 상태 확인
```bash
# 현재 네트워크 인터페이스 확인
ifconfig

# 사용 가능한 모든 인터페이스 확인
ip link show

# TSN 스위치 포트 확인
ls /sys/class/net/ | grep -E "(sw|eth)"
```

## 2. TSN 스위치 포트 활성화

### 2.1 스위치 포트 목록 확인
```bash
# LAN9662의 8개 포트 확인
ip link show | grep sw0p

# 또는
find /sys/class/net -name "sw0p*" -type l
```

### 2.2 포트 1, 2, 3 개별 활성화
```bash
# 포트 1 활성화 (Primary Path)
ip link set sw0p0 up
ip addr add 192.168.1.101/24 dev sw0p0

# 포트 2 활성화 (Secondary Path) 
ip link set sw0p1 up  
ip addr add 192.168.1.102/24 dev sw0p1

# 포트 3 활성화 (Management)
ip link set sw0p2 up
ip addr add 192.168.1.103/24 dev sw0p2

# 상태 확인
ifconfig | grep -A 10 "sw0p"
```

### 2.3 브리지 설정 (FRER용)
```bash
# VLAN-aware 브리지 생성
ip link add name br0 type bridge vlan_filtering 1

# 활성화된 포트들을 브리지에 추가
ip link set sw0p0 master br0
ip link set sw0p1 master br0  
ip link set sw0p2 master br0

# 브리지 IP 설정
ip addr add 192.168.100.1/24 dev br0
ip link set br0 up

# 브리지 상태 확인
bridge link show
bridge vlan show
```

## 3. 기본 연결 테스트

### 3.1 포트별 링크 상태 확인
```bash
# 각 포트의 링크 상태 확인
ethtool sw0p0 | grep "Link detected"
ethtool sw0p1 | grep "Link detected"  
ethtool sw0p2 | grep "Link detected"

# 또는 한번에 확인
for port in sw0p0 sw0p1 sw0p2; do
    echo "=== $port ==="
    ethtool $port | grep -E "(Speed|Duplex|Link detected)"
done
```

### 3.2 외부 장비 연결 테스트
```bash
# 외부 PC와 연결 테스트 (각 포트별)
ping -I sw0p0 -c 5 192.168.1.200  # 외부 장비 IP
ping -I sw0p1 -c 5 192.168.1.200
ping -I sw0p2 -c 5 192.168.1.200

# 브리지를 통한 테스트
ping -I br0 -c 5 192.168.100.200
```

## 4. FRER 기능 테스트 준비

### 4.1 FRER 명령어 확인
```bash
# FRER 툴 사용 가능 여부 확인
which frer
frer --help

# 또는 직접 실행
/usr/bin/frer --help
```

### 4.2 VCAP 툴 확인
```bash
# VCAP 툴 확인
which vcap
vcap --help

# VCAP 규칙 목록 확인
vcap show is1
```

## 5. 단계별 FRER 설정

### 5.1 Stream 100 기본 설정
```bash
# Compound Stream 생성
frer cs add 100

# Recovery Algorithm 설정
frer cs set 100 recovery_algorithm vector
frer cs set 100 recovery_timeout 1000
frer cs set 100 reset_timeout 10000
frer cs set 100 history_length 64

# 설정 확인
frer cs show 100
```

### 5.2 Member Stream 설정
```bash
# Member Stream 할당
frer msa add 101 cs 100  # Primary path
frer msa add 102 cs 100  # Secondary path

# 포트 매핑
frer ms set 101 port sw0p0  # Primary: sw0p0
frer ms set 102 port sw0p1  # Secondary: sw0p1

# Sequence Generation 활성화
frer ms set 101 sequence_generation enable
frer ms set 102 sequence_generation enable

# 설정 확인
frer ms show 101
frer ms show 102
```

### 5.3 Stream Identification 설정
```bash
# MAC 주소 기반 스트림 식별
vcap add is1 rule 10 \
    type ethernet \
    port sw0p0 \
    dmac 01:80:C2:00:00:0E \
    action stream_id 100

vcap add is1 rule 11 \
    type ethernet \
    port sw0p1 \
    dmac 01:80:C2:00:00:0E \
    action stream_id 100

# VCAP 규칙 확인
vcap show is1
```

## 6. FRER 동작 테스트

### 6.1 기본 이중화 테스트
```bash
#!/bin/bash
echo "=== FRER Basic Redundancy Test ==="

# 백그라운드 ping 시작
ping -I br0 192.168.100.200 > ping_results.txt &
PING_PID=$!

# 10초 대기
echo "Running normal traffic for 10 seconds..."
sleep 10

# Primary link 차단
echo "Disabling primary path (sw0p0)..."
ip link set sw0p0 down

# 10초 대기 (Secondary path로 트래픽 흘러야 함)
echo "Testing secondary path for 10 seconds..."
sleep 10

# Primary link 복구
echo "Restoring primary path..."
ip link set sw0p0 up

# 10초 더 대기
echo "Testing recovered redundancy for 10 seconds..."
sleep 10

# 테스트 종료
kill $PING_PID
echo "Test completed. Check ping_results.txt"
```

### 6.2 통계 모니터링
```bash
# 실시간 FRER 통계 모니터링
watch -n 1 "echo '=== CS 100 Statistics ==='; frer cs show 100 statistics"

# 또는 백그라운드 로깅
while true; do
    echo "$(date): $(frer cs show 100 statistics | grep eliminated)"
    sleep 1
done > frer_stats.log &
```

## 7. 성능 측정

### 7.1 지연시간 측정
```bash
# 정밀한 지연시간 측정
ping -I br0 -c 1000 -i 0.01 192.168.100.200 | \
    grep "time=" | \
    awk -F'time=' '{print $2}' | \
    awk -F' ' '{print $1}' > latency_raw.txt

# 통계 계산
awk '{sum+=$1; sumsq+=$1*$1} END {
    mean=sum/NR; 
    stdev=sqrt(sumsq/NR - mean*mean); 
    print "Mean:", mean "ms"; 
    print "StdDev:", stdev "ms"
}' latency_raw.txt
```

### 7.2 처리량 측정
```bash
# iperf3 서버 시작 (원격 장비에서)
# iperf3 -s

# iperf3 클라이언트 테스트 (LAN9662에서)
iperf3 -c 192.168.100.200 -t 30 -i 1 -B 192.168.100.1

# UDP 테스트 (패킷 손실 확인)
iperf3 -c 192.168.100.200 -u -b 100M -t 30
```

## 8. 문제 해결

### 8.1 포트가 안 보이는 경우
```bash
# 드라이버 로딩 확인
lsmod | grep lan966x
dmesg | grep -i lan966x

# 강제 인터페이스 생성
modprobe lan966x_switch
```

### 8.2 FRER 명령어가 없는 경우
```bash
# 패키지 확인
find /usr -name "*frer*" 2>/dev/null
find /bin -name "*frer*" 2>/dev/null

# 수동 설정 방법 (sysfs 사용)
echo "100" > /sys/class/net/br0/bridge/frer_compound_stream
```

이제 단계별로 포트를 활성화하고 FRER 기능을 테스트할 수 있습니다! 🚀