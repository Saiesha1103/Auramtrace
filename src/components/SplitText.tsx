import { Fragment, type ElementType } from 'react';

/**
 * Renders a heading whose words rise out of a mask on scroll (see useReveal).
 * Pass segments so that individual words can be styled (e.g. gold italics).
 */
export interface Segment {
  text: string;
  em?: boolean;
}

interface Props {
  as?: ElementType;
  segments: Segment[];
  className?: string;
  id?: string;
  /** line breaks after these segment indices */
  breakAfter?: number[];
}

export function SplitText({ as: Tag = 'h2', segments, className = 'display', id, breakAfter = [] }: Props) {
  const label = segments.map((s) => s.text).join(' ');
  return (
    <Tag className={className} id={id} data-split aria-label={label}>
      {segments.map((seg, si) => (
        <Fragment key={si}>
          {seg.text.split(' ').map((w, wi) => (
            <Fragment key={wi}>
              <span className="split-line" aria-hidden="true">
                {seg.em ? <em className="split-word">{w}</em> : <span className="split-word">{w}</span>}
              </span>{' '}
            </Fragment>
          ))}
          {breakAfter.includes(si) && <br />}
        </Fragment>
      ))}
    </Tag>
  );
}
