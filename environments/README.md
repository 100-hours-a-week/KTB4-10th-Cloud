# 환경별 배포 값

같은 main 브랜치에서 환경을 디렉토리로 구분합니다.

```
helm/<chart>/templates/          # 공통 Kubernetes 템플릿
environments/staging/*.yaml      # 스테이징 Helm 값
environments/production/         # 운영 Helm 값 (준비 전)
gitops/staging/                  # 스테이징 ESO·인프라·Argo CD 설정
```

예: helm template auth helm/auth -n auth -f environments/staging/auth.yaml
Argo CD source.path는 helm/auth, helm.valueFiles는 ../../environments/staging/auth.yaml입니다.
값 파일은 chart 디렉토리 기준 상대 경로입니다. 두 환경은 main을 읽되 클러스터와 값 파일이 다릅니다.

## 관리 기준

- Helm Application은 main의 environments/staging/<chart>.yaml을 읽도록 전환했습니다.
- 스테이징 설정 변경은 이 환경 파일에서 합니다. helm/*/values.yaml에는 공통 기본값만 둡니다.
- 백엔드 CI는 environments/staging/{auth,guidebook,scheduler}.yaml의 image.tag만 갱신합니다.
- 배포 설정의 변경 이력은 같은 main 브랜치에서 환경 디렉토리별로 관리합니다.
- helm lint/template 명령에도 -f 환경 파일을 지정합니다. 백엔드·Worker는 환경별 이미지 태그 없이 렌더링할 수 없습니다.
- Secret 값은 Git에 저장하지 않고 gitops/<환경>의 ExternalSecret에서 AWS 원본 경로만 참조합니다.
- 운영 설정을 준비할 때 스테이징 값을 통째로 복사하지 않고 운영 도메인·인증서·AWS 경로·리소스 등을 검토합니다.
- 현재 운영 디렉토리는 준비 경로이며 실제 운영 values는 아직 작성하지 않았습니다.

## 이번 정리 반영 순서

1. BE의 기존 chart values 미러 갱신 제거를 dev에 먼저 병합합니다.
2. Cloud의 공통 values 정리 변경을 main에 푸시합니다.
3. Argo CD가 환경별 값을 사용해 이전과 같은 리소스를 렌더링하는지 확인합니다.

기존 namespaces.yaml은 별도 namespace 관리 전환 전까지 호환용으로 유지합니다.
