# FRER 올바른 토폴로지 구성 가이드

## 🚨 현재 구성의 문제점

현재 구현된 구성은 **복제(Replication)만** 수행하고 **제거(Elimination)가 누락**되어 있습니다.

### 현재 상태 (불완전한 FRER)
```
        LAN9662 Switch
PC1 → [eth1] → SGF → [eth2] → PC2
      (입력)   복제 └→[eth3] → PC3
```

**문제점:**
- ✅ 프레임 복제 (SGF): 동작함
- ❌ 중복 제거 (SRF): 구현 안됨
- PC2와 PC3가 **중복된 패킷을 그대로 수신**
- 진정한 FRER이 아닌 단순 브로드캐스트

---

## ✅ 올바른 FRER 토폴로지 옵션

### 옵션 1: 듀얼 스위치 구성 (권장)

```
     송신측 Switch                수신측 Switch
         LAN9662 #1                  LAN9662 #2
            SGF                         SRF
    
PC1 → [eth1] → ┬→ [eth2] ─────────→ [eth2] → ┐
                └→ [eth3] ─────────→ [eth3] → ├→ [eth1] → PC2
                  (Primary)        (Secondary)
```

#### 설정 명령어

**송신측 스위치 (Switch #1):**
```bash
# 브리지 구성
ip link add name br0 type bridge vlan_filtering 1
ip link set eth1 master br0
ip link set eth2 master br0
ip link set eth3 master br0
ip link set br0 up

# VCAP 규칙 - UDP 트래픽 식별
vcap add 1 is1 10 0 VCAP_KFS_5TUPLE_IP4 \
  IF_IGR_PORT_MASK 0x001 0x1ff L3_IP_PROTO 17 0xff \
  VCAP_AFS_S1 ISDX_REPLACE_ENA 1 ISDX_ADD_VAL 1

# FRER Ingress Flow - 복제 활성화
frer iflow 1 --generation 1 --dev1 eth2 --dev2 eth3
```

**수신측 스위치 (Switch #2):**
```bash
# 브리지 구성
ip link add name br0 type bridge vlan_filtering 1
ip link set eth1 master br0
ip link set eth2 master br0
ip link set eth3 master br0
ip link set br0 up

# FRER Egress Flow - 중복 제거 활성화
frer eflow 1 --recovery 1 --dev1 eth2 --dev2 eth3 --out eth1

# 또는 멤버 스트림 설정
frer mstream 1 --port eth2 --handle 100
frer mstream 2 --port eth3 --handle 101
frer cstream 1 --recovery 1 --member 100 --member 101 --out eth1
```

---

### 옵션 2: 단일 스위치 루프백 구성

LAN9662가 8포트이므로 단일 스위치로도 가능합니다:

```
         LAN9662 Switch (8-port)
    
PC1 → [eth1] → SGF → [eth2] ──────┐ (외부 케이블)
                  └→ [eth3] ────┐ │
                                │ │
                                ↓ ↓
PC2 ← [eth4] ← SRF ← [eth5] ←──┘ │
                  └─ [eth6] ←────┘
```

#### 설정 명령어

```bash
# 두 개의 독립적인 브리지 생성
# 송신 브리지 (SGF)
ip link add name br_tx type bridge vlan_filtering 1
ip link set eth1 master br_tx
ip link set eth2 master br_tx
ip link set eth3 master br_tx
ip link set br_tx up

# 수신 브리지 (SRF)
ip link add name br_rx type bridge vlan_filtering 1
ip link set eth4 master br_rx
ip link set eth5 master br_rx
ip link set eth6 master br_rx
ip link set br_rx up

# 송신측 VCAP 및 FRER 설정
vcap add 1 is1 10 0 VCAP_KFS_5TUPLE_IP4 \
  IF_IGR_PORT_MASK 0x001 0x1ff L3_IP_PROTO 17 0xff \
  VCAP_AFS_S1 ISDX_REPLACE_ENA 1 ISDX_ADD_VAL 1

frer iflow 1 --generation 1 --dev1 eth2 --dev2 eth3

# 수신측 FRER 설정
frer eflow 2 --recovery 1 --dev1 eth5 --dev2 eth6 --out eth4

# 외부 루프백 케이블 연결
# eth2 → eth5 (케이블)
# eth3 → eth6 (케이블)
```

---

### 옵션 3: VLAN 기반 논리적 분리

단일 스위치에서 VLAN으로 송수신 경로를 분리:

```
         LAN9662 Switch
    
PC1 → [eth1] → VLAN 10 → SGF → [eth2] VLAN 20 ─┐
                             └→ [eth3] VLAN 30 ─┤
                                                 │
                              ┌─────────────────┘
                              ↓
PC2 ← [eth4] ← VLAN 40 ← SRF ← [eth2,3] VLAN 20,30
```

#### 설정 명령어

```bash
# VLAN aware 브리지
ip link add name br0 type bridge vlan_filtering 1
ip link set eth1 master br0
ip link set eth2 master br0
ip link set eth3 master br0
ip link set eth4 master br0
ip link set br0 up

# VLAN 설정
bridge vlan add vid 10 dev eth1 pvid untagged
bridge vlan add vid 20 dev eth2
bridge vlan add vid 30 dev eth3
bridge vlan add vid 40 dev eth4 pvid untagged

# Ingress VCAP - VLAN 10 트래픽만
vcap add 1 is1 10 0 VCAP_KFS_MAC_VLAN \
  IF_IGR_PORT_MASK 0x001 0x1ff VLAN_ID 10 0xfff \
  VCAP_AFS_S1 ISDX_REPLACE_ENA 1 ISDX_ADD_VAL 1

# Egress VCAP - VLAN 20,30 → VLAN 40
vcap add 2 es0 10 0 VCAP_KFS_MAC_VLAN \
  IF_EGR_PORT_MASK 0x008 0x1ff VLAN_ID 20 0xfff \
  VCAP_AFS_ES0 VID_REPLACE_ENA 1 VID_ADD_VAL 40

# FRER 설정
frer iflow 1 --generation 1 --vlan-out1 20 --vlan-out2 30
frer eflow 1 --recovery 1 --vlan-in1 20 --vlan-in2 30 --vlan-out 40
```

---

## 🔍 검증 방법

### 1. 패킷 생성 (PC1)
```bash
# 단순 UDP 트래픽 생성
sudo mausezahn eth0 -c 100 -d 10ms \
  -t udp sp=5000,dp=5000 -A 10.0.100.1 -B 10.0.100.2
```

### 2. 중간 경로 모니터링 (eth2, eth3)
```bash
# 각 경로에서 R-TAG 확인
sudo tcpdump -i eth2 -nn -e -vvv 'ether proto 0xf1c1'
sudo tcpdump -i eth3 -nn -e -vvv 'ether proto 0xf1c1'
```

### 3. 수신측 검증 (PC2)
```bash
# 중복 제거 확인 - 100개 전송시 100개만 수신되어야 함
sudo tcpdump -i eth0 -nn 'udp port 5000' | wc -l
```

### 4. FRER 통계 확인
```bash
# 송신측 통계
frer iflow 1 --stats
# Frames transmitted: 100
# Frames replicated: 100

# 수신측 통계  
frer eflow 1 --stats
# Frames received: 200
# Frames passed: 100
# Duplicates eliminated: 100
```

---

## ⚠️ 주의사항

### 현재 구성이 불완전한 FRER인 이유

1. **중복 제거 메커니즘 부재**
   - PC2와 PC3가 동일한 패킷을 중복 수신
   - 애플리케이션 레벨에서 중복 처리 필요

2. **시퀀스 복구 기능 미동작**
   - R-TAG는 삽입되지만 활용되지 않음
   - 패킷 순서 보장 메커니즘 없음

3. **장애 복구 테스트 불가**
   - 두 경로가 독립적이지 않음
   - 실제 redundancy 효과 검증 불가

### 완전한 FRER 구현 요구사항

- ✅ **Stream Identification**: VCAP/ISDX 설정
- ✅ **Sequence Generation (SGF)**: R-TAG 삽입, 복제
- ❌ **Sequence Recovery (SRF)**: 중복 제거, 순서 복구
- ❌ **Individual Recovery**: 멤버 스트림 병합
- ❌ **Latent Error Detection**: 시퀀스 불일치 감지

---

## 📝 권장 구현 순서

1. **기본 동작 확인** (현재 상태)
   - 복제 동작 확인
   - R-TAG 삽입 검증

2. **루프백 구성** (옵션 2)
   - 단일 스위치로 전체 파이프라인 테스트
   - SRF 기능 검증

3. **듀얼 스위치** (옵션 1)
   - 실제 네트워크 환경 시뮬레이션
   - 완전한 FRER 데모

4. **장애 시나리오**
   - 케이블 분리 테스트
   - 복구 시간 측정
   - 패킷 손실률 확인

---

## 🎯 결론

현재 구성은 **FRER의 절반만 구현**된 상태입니다. 완전한 FRER 검증을 위해서는:

1. **수신측 SRF 구현** 필수
2. **멤버 스트림 → 컴파운드 스트림** 병합
3. **중복 제거 메커니즘** 활성화

위 옵션 중 하나를 선택하여 구현하면 진정한 FRER 동작을 검증할 수 있습니다.

---

**작성자**: 김현우  
**날짜**: 2025-01-15  
**하드웨어**: Microchip LAN9662 TSN Switch