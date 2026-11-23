-- MVP-04: la RPC puede repetirse si el borrado posterior en Auth quedó pendiente.
begin;

create or replace function public.revoke_eag_invitation(
    p_invitation_id uuid,
    p_organization_id uuid,
    p_actor_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    invited_user_id uuid;
    invitation_status text;
begin
    if not exists (
        select 1 from public.organization_memberships
        where user_id = p_actor_id
          and organization_id = p_organization_id
          and role = 'administrador'
    ) then
        raise exception 'administrator membership required';
    end if;

    -- Serializa revocaciones simultáneas de la misma invitación.
    select provider_user_id, status into invited_user_id, invitation_status
    from public.invitations
    where id = p_invitation_id
      and organization_id = p_organization_id
      and status in ('sent', 'resent', 'revoked')
    for update;

    if invited_user_id is null then
        raise exception 'active invitation not found';
    end if;
    if invitation_status = 'revoked' then
        return;
    end if;

    delete from public.organization_memberships
    where user_id = invited_user_id
      and organization_id = p_organization_id;

    update public.invitations
    set status = 'revoked', updated_at = now(), revoked_at = now(), revoked_by = p_actor_id
    where id = p_invitation_id
      and organization_id = p_organization_id;

    insert into public.audit_events (
        organization_id, actor_id, action, target_user_id, invitation_id
    ) values (
        p_organization_id, p_actor_id, 'invitation_revoked', invited_user_id, p_invitation_id
    );
end;
$$;

-- CREATE OR REPLACE conserva el EXECUTE exclusivo de service_role.
commit;
