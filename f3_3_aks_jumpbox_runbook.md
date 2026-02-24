# F3-3 AKS Jumpbox Runbook

## Scope

- Resource group: `2dt-final-team4`
- Target VNet: `nsc-vnet-dev`
- Target subnet: `nsc-snet-admin`
- Access path: Azure `Bastion` only

## Fixed resource names for 2026-02-24 run

- VM: `jump-aks-20260224-2dt026`
- NIC: `nic-jump-aks-20260224-2dt026`
- OS disk: `osdisk-jump-aks-20260224-2dt026`
- Optional data disk: `datadisk-jump-aks-20260224-2dt026-01`
- Required tags: `owner=2dt026`, `purpose=f3-3-jumpbox`, `ttl=2026-02-24`

## Step 1. Provision private-only jumpbox VM

Create NIC in `nsc-vnet-dev` + `nsc-snet-admin`:

```bash
az network nic create \
  --resource-group 2dt-final-team4 \
  --name nic-jump-aks-20260224-2dt026 \
  --vnet-name nsc-vnet-dev \
  --subnet nsc-snet-admin \
  --tags owner=2dt026 purpose=f3-3-jumpbox ttl=2026-02-24
```

Create VM with no public IP:

```bash
az vm create \
  --resource-group 2dt-final-team4 \
  --name jump-aks-20260224-2dt026 \
  --nics nic-jump-aks-20260224-2dt026 \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --os-disk-name osdisk-jump-aks-20260224-2dt026 \
  --public-ip-address '' \
  --tags owner=2dt026 purpose=f3-3-jumpbox ttl=2026-02-24
```

Optional data disk:

```bash
az vm disk attach \
  --resource-group 2dt-final-team4 \
  --vm-name jump-aks-20260224-2dt026 \
  --name datadisk-jump-aks-20260224-2dt026-01 \
  --new \
  --size-gb 32 \
  --sku StandardSSD_LRS
```

## Step 2. Bastion connection path

From operator workstation:

```bash
az extension show -n ssh || az extension add -n ssh
az network bastion ssh \
  --resource-group 2dt-final-team4 \
  --name nsc-bas-dev \
  --target-resource-id \"$(az vm show -g 2dt-final-team4 -n jump-aks-20260224-2dt026 --query id -o tsv)\" \
  --auth-type ssh-key \
  --username azureuser \
  --ssh-key ~/.ssh/id_rsa
```

If `az network bastion ssh` is unavailable in the current CLI version, use Bastion portal SSH to the same VM.
The precheck command above is mandatory to avoid `The extension ssh is not installed` failures.

## Step 3. AKS private connectivity checks from jumpbox

Check AKS private FQDN:

```bash
az aks show -g 2dt-final-team4 -n nsc-aks-dev --query privateFqdn -o tsv
```

Get kubeconfig and convert auth:

```bash
az aks get-credentials -g 2dt-final-team4 -n nsc-aks-dev --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
```

Readiness checks:

```bash
kubectl cluster-info
kubectl get ns txlookup
```

## Step 4. Evidence logging contract

Store all logs under `.agents/logs/verification/`.

Recommended pilot directory:

`.agents/logs/verification/<timestamp>_f3_3_jumpbox_pilot/`

Recommended file naming:

- `01_provision.log`
- `02_bastion_access.log`
- `03_aks_readiness.log`
- `04_l3_or_blocked_summary.log`

Every evidence file must contain:

- `command`
- `exit_code`
- `UTC timestamp`

## Step 5. Failure handling and rollback

If provisioning, Bastion access, or AKS readiness checks fail, stop further actions.

If explicit requester instruction for cleanup is already given, run the teardown sequence in:

- `docs/ops/f3_3_aks_jumpbox_teardown_runbook.md`

If explicit instruction is not yet given, record `teardown_pending=true` in the pilot summary and keep the resource inventory snapshot in the same evidence directory.
Record the failure reason and rollback result in the same pilot evidence directory.
