require 'yaml'

# Garante o pipeline da imagem própria do ServiceDesk (docs/CI-IMAGEM.md):
# - a imagem é sempre construída sem enterprise/ e verificada antes de publicar;
# - os workflows herdados do upstream não rodam para as branches servicedesk/*.
# Spec puro (sem banco): lê os YAML de .github/workflows.
RSpec.describe 'ServiceDesk CI image workflow' do # rubocop:disable RSpec/DescribeClass
  root = File.expand_path('../..', __dir__)
  workflows_dir = File.join(root, '.github/workflows')

  # Psych lê a chave `on:` como `true` (YAML 1.1); normaliza para 'on'.
  load_workflow = lambda do |name|
    data = YAML.safe_load_file(File.join(workflows_dir, name), aliases: true)
    data['on'] = data.delete(true) if data.key?(true)
    data
  end

  # Simula o filtro de branch do GitHub Actions para um evento (push ou pull_request).
  glob_match = ->(pattern, branch) { File.fnmatch?(pattern, branch, File::FNM_PATHNAME) || File.fnmatch?(pattern, branch) }
  triggers_for = lambda do |trigger, branch|
    config = trigger.is_a?(Hash) ? trigger : {}
    if config['branches']
      config['branches'].any? { |p| glob_match.call(p, branch) }
    elsif config['branches-ignore']
      config['branches-ignore'].none? { |p| glob_match.call(p, branch) }
    else
      true
    end
  end

  describe 'servicedesk-image.yml' do
    let(:workflow) { load_workflow.call('servicedesk-image.yml') }
    let(:steps) { workflow['jobs']['build']['steps'] }
    let(:step_index) { ->(name) { steps.index { |s| s['name'].to_s.start_with?(name) } } }

    it 'roda em push para servicedesk/main e manualmente' do
      expect(workflow['on']['push']['branches']).to eq(['servicedesk/main'])
      expect(workflow['on']).to have_key('workflow_dispatch')
    end

    it 'pede só packages: write e contents: read' do
      expect(workflow['permissions']).to eq('contents' => 'read', 'packages' => 'write')
    end

    it 'remove enterprise/ e marca a edição CE antes do build' do
      strip = steps[step_index.call('Strip enterprise')]
      expect(strip['run']).to include('rm -rf enterprise spec/enterprise')
      expect(strip['run']).to include('CW_EDITION="ce"')
      expect(step_index.call('Strip enterprise')).to be < step_index.call('Build')
    end

    it 'aceita o repositório sem enterprise/ (v3): o rm -rf não falha sem o diretório' do
      strip = steps[step_index.call('Strip enterprise')]
      expect(strip['run']).to include('rm -rf enterprise spec/enterprise')
      expect(strip['run']).to include('test ! -e enterprise')
      expect(File).not_to exist(File.join(root, 'enterprise'))
    end

    it 'verifica a imagem antes de logar e publicar no GHCR' do
      verify = step_index.call('Verify CE image')
      expect(verify).to be > step_index.call('Build')
      expect(verify).to be < step_index.call('Login to GHCR')
      expect(verify).to be < step_index.call('Push')
      expect(steps[verify]['run']).to include('docker/servicedesk/verify-ce-image.sh')
    end

    it 'usa cache de build e o GITHUB_TOKEN no GHCR' do
      build = steps[step_index.call('Build')]['with']
      expect(build['file']).to eq('docker/Dockerfile')
      expect(build['cache-from']).to start_with('type=gha')
      expect(build['cache-to']).to start_with('type=gha')
      login = steps[step_index.call('Login to GHCR')]['with']
      expect(login['registry']).to eq('${{ env.REGISTRY }}')
      expect(workflow['env']['REGISTRY']).to eq('ghcr.io')
      expect(login['password']).to eq('${{ secrets.GITHUB_TOKEN }}')
    end

    it 'publica as tags sha curto e servicedesk-main (esta só na servicedesk/main)' do
      tags = steps[step_index.call('Docker metadata')]['with']['tags']
      expect(tags).to include('type=sha,prefix=,format=short')
      expect(tags).to include("type=raw,value=servicedesk-main,enable=${{ github.ref == 'refs/heads/servicedesk/main' }}")
    end
  end

  describe 'servicedesk-image.yml, job services (sd-ops, qa-pipeline, sd-console)' do
    let(:job) { load_workflow.call('servicedesk-image.yml')['jobs']['services'] }
    let(:steps) { job['steps'] }
    let(:step_index) { ->(name) { steps.index { |s| s['name'].to_s.start_with?(name) } } }
    let(:matrix) { job['strategy']['matrix']['include'] }

    it 'constrói as 3 imagens a partir dos diretórios de cada serviço (com Dockerfile)' do
      expect(matrix.to_h { |m| [m['name'], m['context']] }).to eq(
        'sd-ops' => 'servicedesk/integrations/pbx-bridge',
        'qa-pipeline' => 'servicedesk/integrations/qa-pipeline',
        'sd-console' => 'servicedesk/apps/sd-console'
      )
      matrix.each { |m| expect(File).to exist(File.join(root, m['context'], 'Dockerfile')) }
      expect(job['strategy']['fail-fast']).to be(false)
    end

    it 'testa a imagem antes de logar e publicar' do
      smoke = step_index.call('Smoke test')
      expect(smoke).to be > step_index.call('Build')
      expect(smoke).to be < step_index.call('Login to GHCR')
      expect(smoke).to be < step_index.call('Push')
    end

    it 'usa as mesmas tags do Chatwoot, cache por serviço e o GITHUB_TOKEN' do
      tags = steps[step_index.call('Docker metadata')]['with']['tags']
      expect(tags).to include('type=sha,prefix=,format=short')
      expect(tags).to include("type=raw,value=servicedesk-main,enable=${{ github.ref == 'refs/heads/servicedesk/main' }}")
      expect(steps[step_index.call('Image name')]['run']).to include('${IMAGE_NAME}-${{ matrix.name }}')
      expect(steps[step_index.call('Build')]['with']['cache-to']).to eq('type=gha,mode=max,scope=servicedesk-${{ matrix.name }}')
      expect(steps[step_index.call('Login to GHCR')]['with']['password']).to eq('${{ secrets.GITHUB_TOKEN }}')
    end
  end

  describe 'verify-ce-image.sh' do
    let(:script) { File.read(File.join(root, 'docker/servicedesk/verify-ce-image.sh')) }

    it 'falha se /app/enterprise existir ou se ChatwootApp.enterprise? for verdadeiro' do
      expect(script).to start_with('#!/usr/bin/env bash')
      expect(script).to include('set -euo pipefail')
      expect(script).to include("test ! -e /app/enterprise' || fail")
      expect(script).to include('ChatwootApp.enterprise?')
      expect(script).to include('exit((ent || ext.any?) ? 1 : 0)')
      expect(script).to include('-u DISABLE_ENTERPRISE')
    end
  end

  describe 'workflows herdados do upstream' do
    upstream = Dir.children(workflows_dir).grep(/\.ya?ml\z/) - ['servicedesk-image.yml']
    branches = %w[servicedesk/main servicedesk/release]
    branch_events = %w[push pull_request pull_request_target]

    upstream.each do |file|
      it "#{file} não dispara em push nem em pull request para servicedesk/*" do
        on = load_workflow.call(file)['on']
        events = on.is_a?(Hash) ? on : {}
        names = on.is_a?(Hash) ? on.keys : Array(on)

        branches.product(branch_events).each do |branch, event|
          next unless names.include?(event)

          expect(triggers_for.call(events[event], branch)).to(
            be(false), "#{file}: #{event} dispararia para #{branch}"
          )
        end
      end
    end
  end
end
