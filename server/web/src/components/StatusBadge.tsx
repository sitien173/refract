import React from 'react';
import { JobState } from '../lib/types';
import styles from '../styles/app.module.css';

import circleCheckSvg from '../assets/icons/circle-check.svg';
import triangleAlertSvg from '../assets/icons/triangle-alert.svg';
import wifiOffSvg from '../assets/icons/wifi-off.svg';
import circleXSvg from '../assets/icons/circle-x.svg';
import layersSvg from '../assets/icons/layers.svg';
import activitySvg from '../assets/icons/activity.svg';

export type BadgeState =
  | JobState
  | 'healthy'
  | 'degraded'
  | 'circuit-open'
  | 'circuit-closed'
  | 'circuit-unknown';

interface BadgeConfig {
  label: string;
  icon: string;
  toneClass: string;
}

const badgeConfigs: Record<BadgeState, BadgeConfig> = {
  queued: {
    label: 'Queued',
    icon: layersSvg,
    toneClass: styles.badgeToneNeutral,
  },
  running: {
    label: 'Running',
    icon: activitySvg,
    toneClass: styles.badgeToneInfo,
  },
  succeeded: {
    label: 'Succeeded',
    icon: circleCheckSvg,
    toneClass: styles.badgeToneSuccess,
  },
  failed: {
    label: 'Failed',
    icon: circleXSvg,
    toneClass: styles.badgeToneError,
  },
  cancelled: {
    label: 'Cancelled',
    icon: circleXSvg,
    toneClass: styles.badgeToneError,
  },
  interrupted: {
    label: 'Interrupted',
    icon: triangleAlertSvg,
    toneClass: styles.badgeToneWarning,
  },
  healthy: {
    label: 'Healthy',
    icon: circleCheckSvg,
    toneClass: styles.badgeToneSuccess,
  },
  degraded: {
    label: 'Degraded',
    icon: triangleAlertSvg,
    toneClass: styles.badgeToneWarning,
  },
  'circuit-open': {
    label: 'Circuit Open',
    icon: wifiOffSvg,
    toneClass: styles.badgeToneWarning,
  },
  'circuit-closed': {
    label: 'Closed',
    icon: circleCheckSvg,
    toneClass: styles.badgeToneNeutral,
  },
  'circuit-unknown': {
    label: 'Circuit State Unknown',
    icon: triangleAlertSvg,
    toneClass: styles.badgeToneWarning,
  },
};

interface StatusBadgeProps {
  state: BadgeState;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ state, className }) => {
  const config = badgeConfigs[state] || {
    label: state,
    icon: triangleAlertSvg,
    toneClass: styles.badgeToneNeutral,
  };

  const badgeClass = `${styles.statusBadge} ${config.toneClass} ${className || ''}`.trim();

  return (
    <span className={badgeClass} data-testid={`status-badge-${state}`}>
      <span
        className={styles.statusBadgeIcon}
        style={
          {
            '--icon-url': `url(${config.icon})`,
            maskImage: `url(${config.icon})`,
            WebkitMaskImage: `url(${config.icon})`,
          } as React.CSSProperties
        }
        aria-hidden="true"
      />
      <span className={styles.statusBadgeLabel}>{config.label}</span>
    </span>
  );
};
