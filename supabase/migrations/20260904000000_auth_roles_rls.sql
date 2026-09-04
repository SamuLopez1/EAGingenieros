-- MVP-04: modelo inicial de acceso. Esta migración no crea usuarios ni envía
-- invitaciones; EAG debe aplicarla en un proyecto Supabase autorizado.
begin;

create type public.eag_role as enum ('administrador', 'analista');

create table public.organizations (
    id uuid primary key,
    slug text not null unique check (slug = 'eag'),
    name text not null check (name = 'EAG'),
    created_at timestamptz not null default now()
);

insert into public.organizations (id, slug, name)
values ('00000000-0000-0000-0000-000000000001', 'eag', 'EAG');

create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.organization_memberships (
    user_id uuid primary key references auth.users(id) on delete cascade,
    organization_id uuid not null references public.organizations(id) on delete restrict,
    role public.eag_role not null,
    created_at timestamptz not null default now(),
    created_by uuid references auth.users(id) on delete set null,
    unique (user_id, organization_id)
);

create table public.invitations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    email text not null,
    provider_user_id uuid unique,
    status text not null check (status in ('sent', 'resent', 'revoked', 'accepted', 'expired')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid not null references auth.users(id) on delete restrict,
    revoked_at timestamptz,
    revoked_by uuid references auth.users(id) on delete set null
);

create table public.audit_events (
    id bigint generated always as identity primary key,
    organization_id uuid not null references public.organizations(id) on delete restrict,
    actor_id uuid references auth.users(id) on delete set null,
    action text not null check (action in ('invitation_created', 'invitation_resent', 'invitation_revoked', 'membership_assigned', 'membership_revoked')),
    target_user_id uuid references auth.users(id) on delete set null,
    invitation_id uuid references public.invitations(id) on delete set null,
    occurred_at timestamptz not null default now(),
    metadata jsonb not null default '{}'::jsonb,
    check (jsonb_typeof(metadata) = 'object')
);

-- Estas funciones se ejecutan como propietario para evitar recursión de RLS.
-- Los clientes autenticados solo pueden consultarlas; no aceptan rol ni
-- organización como datos de entrada controlados por el navegador.
create function public.is_eag_member(requested_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_memberships membership
        where membership.user_id = auth.uid()
          and membership.organization_id = requested_organization_id
    );
$$;

create function public.is_eag_administrator(requested_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_memberships membership
        where membership.user_id = auth.uid()
          and membership.organization_id = requested_organization_id
          and membership.role = 'administrador'
    );
$$;

revoke all on function public.is_eag_member(uuid) from public;
revoke all on function public.is_eag_administrator(uuid) from public;
grant execute on function public.is_eag_member(uuid) to authenticated;
grant execute on function public.is_eag_administrator(uuid) to authenticated;

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.organization_memberships enable row level security;
alter table public.invitations enable row level security;
alter table public.audit_events enable row level security;

create policy "members read their organization"
on public.organizations for select to authenticated
using (public.is_eag_member(id));

create policy "users read their own profile"
on public.profiles for select to authenticated
using (id = auth.uid());

create policy "users read own membership and administrators read organization"
on public.organization_memberships for select to authenticated
using (user_id = auth.uid() or public.is_eag_administrator(organization_id));

create policy "administrators read invitations"
on public.invitations for select to authenticated
using (public.is_eag_administrator(organization_id));

create policy "administrators read audit events"
on public.audit_events for select to authenticated
using (public.is_eag_administrator(organization_id));

-- No se definen políticas INSERT, UPDATE ni DELETE para clientes. Las altas,
-- cambios de rol, revocaciones y auditoría solo se harán por backend con una
-- clave de servicio, tras autorización de administrador y validaciones propias.
commit;
