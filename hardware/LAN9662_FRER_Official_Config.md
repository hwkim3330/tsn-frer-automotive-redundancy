# LAN9662 공식 FRER 설정 가이드
*Microchip 공식 문서 기반 (2025.06 BSP)*

## 1. FRER 개요

### 1.1 Microchip LAN9662 FRER 구성요소
- **Stream Identification**: 프레임 필드 기반 스트림 식별
- **Sequence Generation**: 순서 번호 생성  
- **Stream Splitting**: 다중 포트로 스트림 분할
- **Individual Recovery**: 개별 복구 기능
- **Sequence Recovery**: 순서 복구 및 중복 제거

### 1.2 주요 용어
- **Compound Stream (CS)**: 복합 스트림
- **Member Stream (MS)**: 멤버 스트림  
- **Ingress Flow**: 입력 플로우
- **VCAP**: Versatile Content Aware Processor

## 2. 기본 설정

### 2.1 VLAN-aware 브리지 설정
```bash
# VLAN-aware 브리지 생성
ip link add name br0 type bridge vlan_filtering 1

# 포트를 브리지에 추가
ip link set sw0p0 master br0
ip link set sw0p1 master br0
ip link set sw0p2 master br0

# 브리지 활성화
ip link set br0 up
```

### 2.2 VLAN 설정
```bash
# FRER용 VLAN 100 설정
frer vlan add 100 br0
frer vlan set 100 ports sw0p0,sw0p1,sw0p2
```

## 3. FRER 스트림 설정

### 3.1 Compound Stream (복합 스트림) 설정
```bash
# Compound Stream 100 생성
frer cs add 100

# CS에 복구 알고리즘 설정 (Vector Recovery Algorithm)
frer cs set 100 recovery_algorithm vector
frer cs set 100 recovery_timeout 1000  # 1000ms
frer cs set 100 reset_timeout 10000    # 10000ms
```

### 3.2 Member Stream (멤버 스트림) 설정
```bash
# Member Stream 할당
frer msa add 101 cs 100  # MS 101을 CS 100에 할당
frer msa add 102 cs 100  # MS 102를 CS 100에 할당

# Member Stream 설정
frer ms set 101 port sw0p0  # 첫 번째 경로
frer ms set 102 port sw0p1  # 두 번째 경로 (이중화)

# Sequence Generation 활성화
frer ms set 101 sequence_generation enable
frer ms set 102 sequence_generation enable
```

### 3.3 Stream Identification (VCAP 기반)
```bash
# VCAP 설정으로 스트림 식별
vcap add is1 rule 10 \
    type ipv4 \
    port sw0p0 \
    dmac 01:80:C2:00:00:0E \
    action stream_id 100

vcap add is1 rule 11 \
    type ipv4 \
    port sw0p1 \
    dmac 01:80:C2:00:00:0E \
    action stream_id 100
```

### 3.4 Ingress Flow 설정
```bash
# Ingress Flow 설정
frer iflow add 100 port sw0p0 stream_id 100
frer iflow add 100 port sw0p1 stream_id 100

# Flow 우선순위 및 매핑 설정
frer iflow set 100 member_stream 101
frer iflow set 100 member_stream 102
```

## 4. 고급 FRER 설정

### 4.1 Recovery Algorithm 선택
```bash
# Vector Recovery Algorithm (권장)
frer cs set 100 recovery_algorithm vector
frer cs set 100 individual_recovery enable

# Match Recovery Algorithm (대안)
# frer cs set 100 recovery_algorithm match
```

### 4.2 시퀀스 파라미터 튜닝
```bash
# History Length 설정 (기본: 32)
frer cs set 100 history_length 64

# Take-No-Sequence 모드 (선택사항)
frer cs set 100 take_no_sequence disable

# Reset 파라미터
frer cs set 100 reset_timeout 10000
frer cs set 100 invalid_sequence_value 0
```

## 5. FRER 상태 모니터링

### 5.1 통계 확인
```bash
# Compound Stream 통계
frer cs show 100 statistics

# Member Stream 통계  
frer ms show 101 statistics
frer ms show 102 statistics

# 전체 FRER 통계
frer statistics show
```

### 5.2 실시간 모니터링
```bash
# 중복 제거 카운터
watch -n 1 "frer cs show 100 statistics | grep eliminated"

# 시퀀스 오류 모니터링
watch -n 1 "frer cs show 100 statistics | grep sequence_errors"
```

## 6. 실제 테스트 시나리오

### 6.1 Basic Redundancy Test
```bash
#!/bin/bash
# 기본 이중화 테스트

# FRER 설정 적용
frer cs add 100
frer cs set 100 recovery_algorithm vector

frer msa add 101 cs 100
frer msa add 102 cs 100

frer ms set 101 port sw0p0
frer ms set 102 port sw0p1
frer ms set 101 sequence_generation enable
frer ms set 102 sequence_generation enable

# 테스트 트래픽 전송
ping -I br0 192.168.100.200 &
PID=$!

# 5초 후 Primary 링크 차단
sleep 5
ip link set sw0p0 down

# 5초 후 복구
sleep 5
ip link set sw0p0 up

kill $PID
```

### 6.2 Performance Benchmark
```bash
#!/bin/bash
# 성능 벤치마크

echo "=== FRER Performance Test ==="

# 이중화 없는 상태 측정
frer cs set 100 individual_recovery disable
iperf3 -c 192.168.100.200 -t 10 > baseline.txt

# FRER 활성화 후 측정
frer cs set 100 individual_recovery enable
iperf3 -c 192.168.100.200 -t 10 > frer_enabled.txt

echo "Baseline vs FRER comparison:"
diff baseline.txt frer_enabled.txt
```

## 7. 문제 해결

### 7.1 일반적인 문제
```bash
# FRER 설정 확인
frer cs show 100
frer ms show 101
frer ms show 102

# VCAP 규칙 확인
vcap show is1

# 브리지 상태 확인
bridge vlan show
bridge fdb show
```

### 7.2 디버그 로그 활성화
```bash
# FRER 디버그 활성화
echo 8 > /proc/sys/kernel/printk
echo "frer" > /sys/kernel/debug/dynamic_debug/control

# 로그 확인
dmesg | grep -i frer
cat /var/log/messages | grep -i frer
```

## 8. 자동차 애플리케이션 최적화

### 8.1 안전 크리티컬 설정
```bash
# 짧은 복구 시간 (자율주행 적합)
frer cs set 100 recovery_timeout 100    # 100ms
frer cs set 100 reset_timeout 1000      # 1s

# 큰 히스토리 버퍼 (높은 신뢰성)
frer cs set 100 history_length 128
```

### 8.2 실시간 트래픽 우선순위
```bash
# 높은 우선순위 설정
frer ms set 101 priority 7
frer ms set 102 priority 7

# QoS 매핑
frer iflow set 100 pcp 7  # Highest priority
```

이제 실제 LAN9662 하드웨어에서 공식 FRER 기능을 정확하게 테스트할 수 있습니다! 🎯