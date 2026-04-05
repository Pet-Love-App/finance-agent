def call(Map config = [:]) {
    pipeline {
        agent any
        stages {
            stage('Sandbox Static Scan') {
                steps {
                    sh 'python -m agent.sandbox.cli scan --code-file agent/sandbox/orchestrator.py'
                }
            }
            stage('Sandbox Unit Tests') {
                steps {
                    sh 'python -m unittest tests.test_sandbox tests.test_v2_dispatcher'
                }
            }
            stage('SonarQube Gate') {
                steps {
                    sh 'bash ci/sonarqube/sandbox_gate.sh'
                }
            }
        }
    }
}
