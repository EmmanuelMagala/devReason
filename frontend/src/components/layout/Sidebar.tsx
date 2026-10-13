import { NavLink } from 'react-router-dom';
import { LayoutDashboard, FolderGit2, ClipboardCheck, Settings } from 'lucide-react';

export function Sidebar({onNavigate}: {onNavigate?: () => void}) {
  return <nav aria-label="Main navigation" className="space-y-1">{[
    {to: '/', label: 'Overview', icon: LayoutDashboard},
    {to: '/repositories', label: 'Repositories', icon: FolderGit2},
    {to: '/reviews', label: 'Reviews', icon: ClipboardCheck},
    {to: '/settings/integrations', label: 'Settings', icon: Settings},
  ].map(({to, label, icon: Icon}) => <NavLink key={to} to={to} end={to === '/'} onClick={onNavigate} className={({isActive}) => `nav-item ${isActive ? 'nav-active' : ''}`}><Icon size={18} aria-hidden="true" />{label}</NavLink>)}</nav>;
}
