# TSN-FRER 기반 자동차 네트워크 이중화 성능 평가

## 개요
본 연구는 TSN(Time-Sensitive Networking) Switch의 FRER(Frame Replication and Elimination for Reliability) 기능을 활용한 자동차 아키텍처 이중화 기술의 성능을 평가합니다.

## 하드웨어 구성
- **TSN Switch**: Microchip LAN9662 
- **컴퓨팅 플랫폼**: Raspberry Pi CM4 모듈
- **네트워크**: TSN 기반 이더넷 토폴로지

## 연구 목표
1. FRER 기능을 이용한 프레임 복제 및 제거 메커니즘 구현
2. 자동차 네트워크에서의 신뢰성 및 지연시간 성능 측정
3. 실시간 안전 크리티컬 애플리케이션에서의 효과 검증

## 프로젝트 구조
```
├── docs/                 # 연구 논문 및 문서
├── hardware/            # 하드웨어 설정 및 회로도
├── software/            # TSN 설정 및 테스트 소프트웨어
├── results/             # 실험 결과 및 데이터
└── presentations/       # 발표 자료
```

## 논문 발표
- **학회**: 2025 KSAE 춘계학술대회
- **제목**: TSN Switch의 FRER 기능을 이용한 자동차 아키텍처 이중화 기술 및 성능 평가