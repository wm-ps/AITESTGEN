#!/usr/bin/env bash
# Story 2.8 (Production Object Storage on AWS S3) -- Task 2.
#
# Provisions the real AWS resources this story's code (object_store.py,
# ops/k8s/01-configmap.yaml, ops/k8s/08-discovery-worker.yaml) already
# expects: the S3 bucket, and IAM wiring so discovery-worker pods can reach
# it. Requires real AWS credentials and (for the Pod Identity path)
# cluster-admin on the target EKS cluster -- neither exists in a plain dev
# checkout, which is why this is a script to run, not code that runs itself.
#
# Usage:
#   AWS_REGION=us-east-1 \
#   BUCKET_NAME=aitestgen-discovery-evidence-prod \
#   CLUSTER_NAME=aitestgen-prod \
#   ./provision-s3-object-storage.sh
#
# Then:
#   - Put BUCKET_NAME into ops/k8s/01-configmap.yaml's AWS_S3_BUCKET
#     (replacing the REPLACE_S3_BUCKET_NAME placeholder).
#   - If Pod Identity association succeeded (default path below), remove
#     the AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY secretKeyRef entries from
#     ops/k8s/08-discovery-worker.yaml and add:
#       spec.template.spec.serviceAccountName: discovery-worker
#     with a matching ServiceAccount object (no annotation needed -- Pod
#     Identity associates by cluster+namespace+service-account name, not
#     an annotated role ARN like IRSA).
#   - Only if this cluster doesn't support Pod Identity (see the
#     SKIP_POD_IDENTITY fallback below): populate AWS_ACCESS_KEY_ID/
#     AWS_SECRET_ACCESS_KEY in the aitestgen-secrets Secret from an IAM
#     user's access key instead, and leave ops/k8s/08-discovery-worker.yaml's
#     existing secretKeyRef entries as-is.

set -euo pipefail

AWS_REGION="${AWS_REGION:?set AWS_REGION, e.g. us-east-1}"
BUCKET_NAME="${BUCKET_NAME:?set BUCKET_NAME, e.g. aitestgen-discovery-evidence-prod}"
CLUSTER_NAME="${CLUSTER_NAME:-}"
NAMESPACE="${NAMESPACE:-aitestgen}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-discovery-worker}"
ROLE_NAME="${ROLE_NAME:-aitestgen-discovery-worker-s3}"
SKIP_POD_IDENTITY="${SKIP_POD_IDENTITY:-false}"

echo "== Creating bucket: ${BUCKET_NAME} (${AWS_REGION}) =="
if [[ "${AWS_REGION}" == "us-east-1" ]]; then
  aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}"
else
  aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}" \
    --create-bucket-configuration LocationConstraint="${AWS_REGION}"
fi

echo "== Blocking all public access =="
aws s3api put-public-access-block --bucket "${BUCKET_NAME}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "== Enabling default SSE-S3 encryption =="
aws s3api put-bucket-encryption --bucket "${BUCKET_NAME}" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DiscoveryWorkerObjectReadWrite",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/discovery-runs/*"
    }
  ]
}
EOF
)

if [[ "${SKIP_POD_IDENTITY}" == "true" ]]; then
  echo "== SKIP_POD_IDENTITY=true -- bucket is ready, no IAM role/association created =="
  echo "Create an IAM user + access key by hand and populate aitestgen-secrets with"
  echo "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, scoped to the read/write policy below:"
  echo "${POLICY_DOC}"
  exit 0
fi

: "${CLUSTER_NAME:?set CLUSTER_NAME for Pod Identity association, or set SKIP_POD_IDENTITY=true for the access-key fallback}"

echo "== Creating least-privilege IAM policy =="
POLICY_ARN=$(aws iam create-policy \
  --policy-name "${ROLE_NAME}-policy" \
  --policy-document "${POLICY_DOC}" \
  --query 'Policy.Arn' --output text)

echo "== Creating IAM role trusted by EKS Pod Identity =="
TRUST_DOC='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "pods.eks.amazonaws.com"},
      "Action": ["sts:AssumeRole", "sts:TagSession"]
    }
  ]
}'
ROLE_ARN=$(aws iam create-role \
  --role-name "${ROLE_NAME}" \
  --assume-role-policy-document "${TRUST_DOC}" \
  --query 'Role.Arn' --output text)

aws iam attach-role-policy --role-name "${ROLE_NAME}" --policy-arn "${POLICY_ARN}"

echo "== Associating the role with the discovery-worker ServiceAccount via Pod Identity =="
aws eks create-pod-identity-association \
  --cluster-name "${CLUSTER_NAME}" \
  --namespace "${NAMESPACE}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --role-arn "${ROLE_ARN}"

echo "== Done =="
echo "Bucket: ${BUCKET_NAME}"
echo "Role:   ${ROLE_ARN}"
echo "Next: set AWS_S3_BUCKET=${BUCKET_NAME} in ops/k8s/01-configmap.yaml, add a"
echo "ServiceAccount named '${SERVICE_ACCOUNT}' in namespace '${NAMESPACE}', set it as"
echo "serviceAccountName in ops/k8s/08-discovery-worker.yaml, and remove the"
echo "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY secretKeyRef entries there."
