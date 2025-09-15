# LAN9662 올바른 인터페이스 설정 가이드

## 1. LAN9662 인터페이스 확인

### 1.1 사용 가능한 인터페이스 확인
```bash
# 모든 네트워크 인터페이스 확인
ip link show

# 이더넷 인터페이스만 확인
ip link show | grep -E "eth[0-9]"

# LAN9662 포트들 확인 (eth1, eth2, eth3, ...)
ls /sys/class/net/ | grep eth
```

## 2. eth1, eth2, eth3 포트 활성화

### 2.1 개별 포트 활성화
```bash
# eth1 활성화 (Primary Path)
ip link set eth1 up
ip addr add 192.168.1.101/24 dev eth1

# eth2 활성화 (Secondary Path)  
ip link set eth2 up
ip addr add 192.168.1.102/24 dev eth2

# eth3 활성화 (Management/Test)
ip link set eth3 up
ip addr add 192.168.1.103/24 dev eth3

# 상태 확인
ifconfig | grep -A 10 "eth[1-3]"
```

### 2.2 링크 상태 확인
```bash
# 각 포트의 링크 상태 확인
for port in eth1 eth2 eth3; do
    echo "=== $port ==="
    ethtool $port | grep -E "(Speed|Duplex|Link detected)" 2>/dev/null || echo "No cable connected"
done
```

## 3. FRER을 위한 브리지 설정

### 3.1 VLAN-aware 브리지 생성
```bash
# 브리지 생성
ip link add name br0 type bridge vlan_filtering 1

# eth1, eth2를 이중화 경로로 브리지에 추가
ip link set eth1 master br0
ip link set eth2 master br0

# 브리지 IP 설정
ip addr add 192.168.100.1/24 dev br0
ip link set br0 up

# 브리지 상태 확인
bridge link show
```

### 3.2 VLAN 설정 (FRER용)
```bash
# VLAN 100 추가 (FRER 스트림용)
bridge vlan add vid 100 dev eth1
bridge vlan add vid 100 dev eth2
bridge vlan add vid 100 dev br0 self

# VLAN 설정 확인
bridge vlan show
```

## 4. FRER 설정 (올바른 인터페이스 사용)

### 4.1 Stream Identification 설정
```bash
# VCAP 규칙으로 스트림 식별 (eth1, eth2 사용)
vcap add is1 rule 10 \
    type ethernet \
    port eth1 \
    vid 100 \
    action stream_id 100

vcap add is1 rule 11 \
    type ethernet \
    port eth2 \
    vid 100 \
    action stream_id 100
```

### 4.2 FRER Compound Stream 설정
```bash
# Compound Stream 100 생성
frer cs add 100
frer cs set 100 recovery_algorithm vector
frer cs set 100 recovery_timeout 1000
frer cs set 100 reset_timeout 10000
frer cs set 100 history_length 64
```

### 4.3 Member Stream 설정 (eth1, eth2 사용)
```bash
# Member Stream 할당
frer msa add 101 cs 100  # eth1용
frer msa add 102 cs 100  # eth2용

# 포트 매핑
frer ms set 101 port eth1  # Primary path
frer ms set 102 port eth2  # Secondary path

# Sequence Generation 활성화
frer ms set 101 sequence_generation enable
frer ms set 102 sequence_generation enable

# 설정 확인
frer ms show 101
frer ms show 102
```

## 5. 연결 테스트

### 5.1 기본 연결 확인
```bash
# eth1을 통한 ping 테스트
ping -I eth1 -c 5 192.168.1.200

# eth2를 통한 ping 테스트  
ping -I eth2 -c 5 192.168.1.200

# 브리지를 통한 ping 테스트
ping -I br0 -c 5 192.168.100.200
```

### 5.2 FRER 이중화 테스트
```bash
#!/bin/bash
echo "=== FRER Redundancy Test ==="

# 백그라운드 ping 시작 (브리지 통해서)
ping -I br0 192.168.100.200 > ping_test.txt &
PING_PID=$!

# 정상 상태에서 10초 대기
echo "Normal operation for 10 seconds..."
sleep 10

# eth1 (Primary) 차단
echo "Disabling primary path (eth1)..."
ip link set eth1 down

# Secondary path로 10초 테스트
echo "Testing secondary path (eth2) for 10 seconds..."
sleep 10

# eth1 복구
echo "Restoring primary path (eth1)..."
ip link set eth1 up

# 복구된 상태에서 10초 테스트
echo "Testing recovered redundancy for 10 seconds..."
sleep 10

# 테스트 종료
kill $PING_PID
echo "Test completed. Results in ping_test.txt"

# 패킷 손실률 확인
grep "packet loss" ping_test.txt
```

## 6. FRER 통계 모니터링

### 6.1 실시간 통계 확인
```bash
# FRER 통계 실시간 모니터링
watch -n 1 "frer cs show 100 statistics"

# 중복 제거 카운터만 확인
watch -n 1 "frer cs show 100 statistics | grep -E '(eliminated|sequence_errors)'"
```

### 6.2 포트별 통계 확인
```bash
# eth1, eth2 트래픽 통계
cat /sys/class/net/eth1/statistics/rx_packets
cat /sys/class/net/eth1/statistics/tx_packets
cat /sys/class/net/eth2/statistics/rx_packets  
cat /sys/class/net/eth2/statistics/tx_packets
```

## 7. 성능 측정 스크립트

### 7.1 지연시간 측정
```bash
#!/bin/bash
echo "=== Latency Measurement ==="

# FRER 비활성화 상태 측정
frer cs set 100 individual_recovery disable
echo "Measuring baseline latency (FRER OFF)..."
ping -I br0 -c 100 -i 0.01 192.168.100.200 | grep "time=" > latency_baseline.txt

# FRER 활성화 상태 측정
frer cs set 100 individual_recovery enable
echo "Measuring FRER latency (FRER ON)..."
ping -I br0 -c 100 -i 0.01 192.168.100.200 | grep "time=" > latency_frer.txt

# 결과 분석
echo "=== Results ==="
echo "Baseline (FRER OFF):"
awk -F'time=' '{print $2}' latency_baseline.txt | awk -F' ' '{sum+=$1; count++} END {print "Average:", sum/count "ms"}'

echo "FRER ON:"
awk -F'time=' '{print $2}' latency_frer.txt | awk -F' ' '{sum+=$1; count++} END {print "Average:", sum/count "ms"}'
```

## 8. 문제 해결

### 8.1 인터페이스가 안 보이는 경우
```bash
# 드라이버 상태 확인
lsmod | grep lan966x
dmesg | grep -i "lan966x\|eth"

# 네트워크 매니저 확인 (있다면 비활성화)
systemctl status networkd 2>/dev/null || echo "No networkd"
systemctl status NetworkManager 2>/dev/null || echo "No NetworkManager"
```

### 8.2 FRER 명령어 확인
```bash
# FRER 툴 위치 확인
which frer || find /usr -name "*frer*" 2>/dev/null

# 수동으로 실행해보기
/usr/bin/frer --help 2>/dev/null || echo "FRER tool not found"
```

이제 올바른 `eth1`, `eth2`, `eth3` 인터페이스를 사용해서 FRER 테스트를 진행할 수 있습니다! 🎯