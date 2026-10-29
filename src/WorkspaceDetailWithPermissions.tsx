import React, { useState, useEffect, useRef } from 'react';
import './WorkspaceDetailPermissions.css';

type User = { id: string; email: string; display_name?: string };
type UiPermissions = {
  all_commands: boolean;
  can_file: boolean;
  can_home: boolean;
  can_view: boolean;
  can_share: boolean;
  can_pdf: boolean;
  can_ppt: boolean;
  can_refresh: boolean;
  can_subscribe: boolean;
  can_alert: boolean;
  can_download: boolean;
};
type Member = {
  user_id: string;
  role: string;
  is_owner?: boolean;
  vtab_users?: User;
  access_sources?: string[];
  ui_permissions?: UiPermissions;
};

const DEFAULTS: UiPermissions = {
  all_commands: true,
  can_file: true,
  can_home: true,
  can_view: true,
  can_share: true,
  can_pdf: true,
  can_ppt: true,
  can_refresh: true,
  can_subscribe: true,
  can_alert: true,
  can_download: true,
};

const OPTIONS: Array<{ key: keyof UiPermissions; label: string }> = [
  { key: 'can_file', label: 'File menu' },
  { key: 'can_home', label: 'Home ribbon' },
  { key: 'can_view', label: 'View ribbon' },
  { key: 'can_share', label: 'Share' },
  { key: 'can_pdf', label: 'PDF' },
  { key: 'can_ppt', label: 'PowerPoint' },
  { key: 'can_refresh', label: 'Refresh' },
  { key: 'can_subscribe', label: 'Subscribe' },
  { key: 'can_alert', label: 'Alerts' },
  { key: 'can_download', label: 'Download project' },
];

const ROLES = ['Viewer', 'Contributor', 'Member', 'Admin'];

const ROLE_DETAILS = [
  { name: 'Viewer', desc: 'Can view, interact with, and export published reports' },
  { name: 'Contributor', desc: 'Can publish, edit, update, and manage workspace reports' },
  { name: 'Member', desc: 'Standard team member with view, edit, and share permissions' },
  { name: 'Admin', desc: 'Full control over workspace settings, permissions, and members' },
];

function Switch({
  checked,
  label,
  disabled,
  onChange,
}: {
  checked: boolean;
  label: string;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className={'uiPermissionSwitch ' + (disabled ? 'disabled' : '')}>
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        className={checked ? 'on' : ''}
        onClick={() => onChange(!checked)}
      >
        <i />
      </button>
    </label>
  );
}

function UserIdentity({ user }: { user: User }) {
  const name = user.display_name || user.email || user.id;
  const initials = name
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((value) => value[0]?.toUpperCase())
    .join('');
  return (
    <div className="identity">
      <div className="avatar light">{initials || 'U'}</div>
      <div>
        <b>{name}</b>
        <small>{user.email}</small>
      </div>
    </div>
  );
}

function Badge({ children, tone = 'blue' }: { children: React.ReactNode; tone?: string }) {
  return <span className={'badge ' + tone}>{children}</span>;
}

export default function WorkspaceDetailWithPermissions(props: any) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [selectedUserForRole, setSelectedUserForRole] = useState<User | null>(null);
  const [chosenRole, setChosenRole] = useState<string>('Viewer');
  const [isAdding, setIsAdding] = useState(false);
  const [addSuccess, setAddSuccess] = useState(false);
  const [addError, setAddError] = useState('');

  const searchBoxRef = useRef<HTMLDivElement>(null);

  // Available users not yet in this workspace
  const available = (props.users || []).filter(
    (user: User) => !(props.members || []).some((member: Member) => member.user_id === user.id)
  );

  // Filtered users matching search query
  const filteredUsers = available.filter((user: User) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase().trim();
    const name = (user.display_name || '').toLowerCase();
    const email = (user.email || '').toLowerCase();
    return name.includes(q) || email.includes(q);
  });

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target as Node)) {
        setIsSearchOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectUser = (user: User) => {
    setSelectedUserForRole(user);
    setChosenRole('Viewer');
    setAddError('');
    setAddSuccess(false);
    setIsSearchOpen(false);
  };

  const handleConfirmAdd = async () => {
    if (!selectedUserForRole) return;
    setIsAdding(true);
    setAddError('');
    try {
      if (typeof props.onAddUsers === 'function') {
        await props.onAddUsers([selectedUserForRole.id], chosenRole);
      }
      setAddSuccess(true);
      setTimeout(() => {
        setSelectedUserForRole(null);
        setSearchQuery('');
        setAddSuccess(false);
        setIsAdding(false);
      }, 600);
    } catch (err: any) {
      setAddError(err?.message || 'Failed to add user to workspace');
      setIsAdding(false);
    }
  };

  return (
    <>
      <button className="back" onClick={props.onBack}>
        ← All workspaces
      </button>

      <div className="detail-hero">
        <div className="workspace-icon">▦</div>
        <div>
          <span className="eyebrow">TEAM WORKSPACE</span>
          <h2>{props.workspace.name}</h2>
          <p>
            {props.workspace.owner?.display_name || props.workspace.owner?.email} ·{' '}
            {props.members.length} members
          </p>
        </div>
      </div>

      <div className="two-col wide-left">
        <section className="panel">
          <div className="panel-head">
            <h2>Members and access</h2>
          </div>

          {/* Search Box with Live Suggestions */}
          <div className="member-search-box-wrap" ref={searchBoxRef}>
            <div className="member-search-bar">
              <span className="search-bar-icon">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </span>
              <input
                type="text"
                className="member-search-input"
                placeholder="Search user by name or email to add..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setIsSearchOpen(true);
                }}
                onFocus={() => setIsSearchOpen(true)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => {
                    setSearchQuery('');
                    setIsSearchOpen(false);
                  }}
                  title="Clear search"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Suggestions Dropdown */}
            {isSearchOpen && (
              <div className="member-suggestions-dropdown">
                <div className="suggestions-status-bar">
                  <span>
                    {filteredUsers.length} user{filteredUsers.length === 1 ? '' : 's'} available to add
                  </span>
                  {searchQuery && <small>Filtering by "{searchQuery}"</small>}
                </div>
                <div className="suggestions-list-scroll">
                  {filteredUsers.length > 0 ? (
                    filteredUsers.map((user: User) => {
                      const name = user.display_name || user.email;
                      const initials = name
                        .split(/\s+|@/)
                        .filter(Boolean)
                        .slice(0, 2)
                        .map((v) => v[0]?.toUpperCase())
                        .join('');
                      return (
                        <div
                          key={user.id}
                          className="suggestion-row"
                          onClick={() => handleSelectUser(user)}
                        >
                          <div className="avatar light">{initials || 'U'}</div>
                          <div className="suggestion-text">
                            <span className="suggestion-name">{name}</span>
                            <span className="suggestion-email">{user.email}</span>
                          </div>
                          <button type="button" className="suggestion-add-btn">
                            + Add
                          </button>
                        </div>
                      );
                    })
                  ) : (
                    <div className="suggestions-empty">
                      {available.length === 0
                        ? 'All registered users are already members of this workspace.'
                        : `No users match "${searchQuery}"`}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Source</th>
                <th>Role</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {props.members.map((member: Member) => {
                const owner =
                  member.is_owner ||
                  (props.workspace.owner?.id && member.user_id === props.workspace.owner.id);
                return (
                  <tr key={member.user_id}>
                    <td>
                      <UserIdentity
                        user={member.vtab_users || { id: member.user_id, email: member.user_id }}
                      />
                    </td>
                    <td>
                      {owner ? (
                        <Badge tone="purple">Owner</Badge>
                      ) : (
                        (member.access_sources || ['Direct']).map((source) => (
                          <Badge key={source} tone={source === 'Direct' ? 'blue' : 'purple'}>
                            {source}
                          </Badge>
                        ))
                      )}
                    </td>
                    <td>
                      {owner ? (
                        <Badge tone="green">Owner</Badge>
                      ) : (
                        <select
                          value={member.role}
                          onChange={(event) => props.onRole(member.user_id, event.target.value)}
                        >
                          {ROLES.map((role) => (
                            <option key={role}>{role}</option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>
                      {!owner && (
                        <button
                          className="danger-link"
                          onClick={() => props.onRemove(member.user_id)}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <div>
          <section className="panel">
            <div className="panel-head">
              <h2>Assign an access group</h2>
            </div>
            <label className="field">
              <span>Group</span>
              <select
                value={props.form.group_id || ''}
                onChange={(event) =>
                  props.setForm((form: any) => ({ ...form, group_id: event.target.value }))
                }
              >
                <option value="">Select group</option>
                {props.groups.map((group: any) => (
                  <option key={group.id} value={group.id}>
                    {group.name} ({group.member_count})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Workspace role</span>
              <select
                value={props.form.role || 'Viewer'}
                onChange={(event) =>
                  props.setForm((form: any) => ({ ...form, role: event.target.value }))
                }
              >
                {ROLES.map((role) => (
                  <option key={role}>{role}</option>
                ))}
              </select>
            </label>
            <button
              className="primary wide"
              disabled={!props.form.group_id}
              onClick={props.onAssignGroup}
            >
              Assign group
            </button>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Notification routing</h2>
            </div>
            {[
              ['scheduler', 'Refresh notifications'],
              ['alert', 'Data alerts'],
              ['subscription', 'Email subscriptions'],
            ].map(([key, label]) => (
              <label className="field" key={key}>
                <span>{label}</span>
                <select
                  value={props.form[key] || 'all_members'}
                  onChange={(event) =>
                    props.setForm((form: any) => ({ ...form, [key]: event.target.value }))
                  }
                >
                  <option value="all_members">All workspace members</option>
                  <option value="owner_only">Workspace owner only</option>
                </select>
              </label>
            ))}
            <button className="secondary wide" onClick={props.onPolicy}>
              Save routing
            </button>
          </section>
        </div>
      </div>

      {/* Permissions switches section */}
      <section className="panel">
        <div className="panel-head">
          <h2>Report command permissions</h2>
        </div>
        <p className="uiPermissionHelp">
          Disabled commands stay visible in Reporting Services, but are greyed out and cannot be used.
        </p>
        <div className="uiPermissionMembers">
          {props.members.map((member: Member) => {
            const owner =
              member.is_owner ||
              (props.workspace.owner?.id && member.user_id === props.workspace.owner.id);
            const permissions = { ...DEFAULTS, ...(member.ui_permissions || {}) };
            const allEnabled = OPTIONS.every((option) => permissions[option.key] !== false);
            const save = (next: UiPermissions) => props.onUiPermissions(member.user_id, next);
            return (
              <article className="uiPermissionMember" key={member.user_id}>
                <div className="uiPermissionIdentity">
                  <UserIdentity
                    user={member.vtab_users || { id: member.user_id, email: member.user_id }}
                  />
                  <Badge tone={owner ? 'green' : 'blue'}>{owner ? 'Owner' : member.role}</Badge>
                </div>
                <div className="uiPermissionMaster">
                  <Switch
                    checked={allEnabled}
                    label="All report commands"
                    disabled={owner}
                    onChange={(enabled) =>
                      save({
                        ...permissions,
                        all_commands: enabled,
                        ...Object.fromEntries(OPTIONS.map((option) => [option.key, enabled])),
                      } as UiPermissions)
                    }
                  />
                </div>
                <div className="uiPermissionGrid">
                  {OPTIONS.map((option) => (
                    <Switch
                      key={option.key}
                      checked={permissions[option.key] !== false}
                      label={option.label}
                      disabled={owner}
                      onChange={(enabled) => {
                        const next = { ...permissions, [option.key]: enabled } as UiPermissions;
                        next.all_commands = OPTIONS.every((item) => next[item.key] !== false);
                        save(next);
                      }}
                    />
                  ))}
                </div>
                {owner && <small>Workspace owners always retain every command.</small>}
              </article>
            );
          })}
        </div>
      </section>

      {/* Role Assignment Modal with Loading Animation */}
      {selectedUserForRole && (
        <div
          className="modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isAdding) setSelectedUserForRole(null);
          }}
        >
          <div className="modal role-modal" role="dialog" aria-modal="true">
            <div className="modal-head">
              <h2>Add Member to Workspace</h2>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => {
                  if (!isAdding) setSelectedUserForRole(null);
                }}
                disabled={isAdding}
                title="Close"
              >
                ✕
              </button>
            </div>

            <div className="target-user-banner">
              <div className="avatar light large">
                {(selectedUserForRole.display_name || selectedUserForRole.email)
                  .split(/\s+|@/)
                  .filter(Boolean)
                  .slice(0, 2)
                  .map((v) => v[0]?.toUpperCase())
                  .join('') || 'U'}
              </div>
              <div className="target-user-meta">
                <strong>{selectedUserForRole.display_name || selectedUserForRole.email}</strong>
                <small>{selectedUserForRole.email}</small>
              </div>
            </div>

            <div className="role-question-box">
              <label className="role-question-heading">
                Which role should this user be given?
              </label>
              <div className="role-cards-list">
                {ROLE_DETAILS.map((r) => {
                  const active = chosenRole === r.name;
                  return (
                    <div
                      key={r.name}
                      className={`role-select-card ${active ? 'active' : ''} ${
                        isAdding ? 'disabled' : ''
                      }`}
                      onClick={() => {
                        if (!isAdding) setChosenRole(r.name);
                      }}
                    >
                      <div className="role-radio-ring">
                        {active && <div className="role-radio-core" />}
                      </div>
                      <div className="role-desc-group">
                        <div className="role-name-row">
                          <span className="role-name-text">{r.name}</span>
                          {r.name === 'Viewer' && <span className="default-role-tag">Default</span>}
                        </div>
                        <p className="role-desc-text">{r.desc}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {addError && <div className="notice error">{addError}</div>}
            {addSuccess && (
              <div className="notice success">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                User added successfully as <strong>{chosenRole}</strong>!
              </div>
            )}

            <div className="modal-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setSelectedUserForRole(null)}
                disabled={isAdding}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`primary role-confirm-btn ${isAdding ? 'loading' : ''} ${
                  addSuccess ? 'success' : ''
                }`}
                onClick={handleConfirmAdd}
                disabled={isAdding || addSuccess}
              >
                {isAdding ? (
                  <>
                    <svg
                      className="admin-spinner"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.25)" strokeWidth="3" />
                      <path
                        d="M12 2a10 10 0 0 1 10 10"
                        stroke="#ffffff"
                        strokeWidth="3"
                        strokeLinecap="round"
                      />
                    </svg>
                    <span>Adding user...</span>
                  </>
                ) : addSuccess ? (
                  <span>✓ Added!</span>
                ) : (
                  <span>Add as {chosenRole}</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
