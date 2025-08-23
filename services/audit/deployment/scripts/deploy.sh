#!/bin/bash
# A.27 Audit Service Deployment Script

set -e

echo "🚀 Deploying A.27 Audit Service to production..."

# Configuration
NAMESPACE="anumate-audit"
IMAGE_TAG=${IMAGE_TAG:-"1.0.0"}
DOCKER_REGISTRY=${DOCKER_REGISTRY:-"your-registry.com"}

# Functions
check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    if ! command -v kubectl &> /dev/null; then
        echo "❌ kubectl is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo "❌ docker is not installed"
        exit 1
    fi
    
    echo "✅ Dependencies check passed"
}

build_and_push_image() {
    echo "🏗️ Building and pushing Docker image..."
    
    docker build -t ${DOCKER_REGISTRY}/anumate/audit-service:${IMAGE_TAG} .
    docker push ${DOCKER_REGISTRY}/anumate/audit-service:${IMAGE_TAG}
    
    echo "✅ Docker image built and pushed"
}

deploy_to_kubernetes() {
    echo "☸️ Deploying to Kubernetes..."
    
    # Apply Kubernetes configurations
    kubectl apply -f deployment/kubernetes/01-namespace.yaml
    kubectl apply -f deployment/kubernetes/02-configmap.yaml
    kubectl apply -f deployment/kubernetes/03-secret.yaml
    kubectl apply -f deployment/kubernetes/04-pvc.yaml
    kubectl apply -f deployment/kubernetes/05-deployment.yaml
    kubectl apply -f deployment/kubernetes/06-service.yaml
    
    # Wait for deployment to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/audit-service -n ${NAMESPACE}
    
    echo "✅ Kubernetes deployment completed"
}

run_database_migrations() {
    echo "🗃️ Running database migrations..."
    
    # Get a pod to run migrations
    POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=audit-service -o jsonpath="{.items[0].metadata.name}")
    
    if [ ! -z "$POD_NAME" ]; then
        kubectl exec -n ${NAMESPACE} ${POD_NAME} -- alembic upgrade head
        echo "✅ Database migrations completed"
    else
        echo "⚠️ No pods found to run migrations"
    fi
}

verify_deployment() {
    echo "🔍 Verifying deployment..."
    
    # Check service status
    kubectl get deployments -n ${NAMESPACE}
    kubectl get services -n ${NAMESPACE}
    kubectl get pods -n ${NAMESPACE}
    
    # Test health endpoint
    echo "Testing health endpoint..."
    SERVICE_IP=$(kubectl get service audit-service -n ${NAMESPACE} -o jsonpath="{.spec.clusterIP}")
    
    # Port forward for testing (in background)
    kubectl port-forward service/audit-service -n ${NAMESPACE} 8007:80 &
    PORT_FORWARD_PID=$!
    sleep 5
    
    if curl -f http://localhost:8007/health; then
        echo "✅ Health check passed"
    else
        echo "❌ Health check failed"
        kill $PORT_FORWARD_PID
        exit 1
    fi
    
    kill $PORT_FORWARD_PID
}

# Main execution
main() {
    echo "Starting A.27 Audit Service deployment..."
    
    check_dependencies
    build_and_push_image
    deploy_to_kubernetes
    run_database_migrations
    verify_deployment
    
    echo "🎉 A.27 Audit Service deployment completed successfully!"
    echo "Service is available at: audit-service.anumate-audit.svc.cluster.local"
}

# Execute main function
main "$@"
