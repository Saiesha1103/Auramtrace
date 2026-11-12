import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { scrollToId } from '../lib/useSmoothScroll';
import './Button.css';

interface Props extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: 'gold' | 'ghost';
  icon?: IconName;
  iconLeft?: IconName;
  size?: 'md' | 'lg';
  children: ReactNode;
}

/** Link-styled CTA. In-page `#hash` targets scroll smoothly. */
export function Button({ variant = 'gold', icon, iconLeft, size = 'md', className = '', href, onClick, children, ...rest }: Props) {
  return (
    <a
      href={href}
      className={`btn btn-${variant} btn-${size} ${className}`}
      onClick={(e) => {
        onClick?.(e);
        if (href?.startsWith('#') && href.length > 1 && !e.defaultPrevented) {
          e.preventDefault();
          scrollToId(href.slice(1));
        }
      }}
      {...rest}
    >
      {iconLeft && <Icon name={iconLeft} size={20} />}
      <span>{children}</span>
      {icon && <Icon name={icon} size={18} className="btn-icon-trail" />}
    </a>
  );
}
