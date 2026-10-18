# ansible — secrets (decisão D4)

Senhas via **ansible-vault**. A senha do vault é **uma única variável**:

- **Local:** `.ansible.vault_pass` na raiz do repo — **gitignored**, nunca versionada.
- **GitHub:** secret `ANSIBLE_VAULT_PASSWORD` (já setado no repo).

Uso:
```bash
# criar/editar segredos cifrados
ansible-vault edit  ansible/group_vars/all/vault.yml --vault-password-file .ansible.vault_pass
# em CI, a senha vem do secret:
printf '%s' "$ANSIBLE_VAULT_PASSWORD" > .ansible.vault_pass
```

Regra: **nenhum segredo em texto claro no git**. Em dev, valores de brincadeira no `docker-compose.yml`;
em prod, tudo pelo vault. Um vault por empresa (tenant, D17).
