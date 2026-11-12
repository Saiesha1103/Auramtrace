import { Icon } from '../components/Icon';
import { CUSTODY_NODES, nodeLabelEls } from '../three/nodes';

/** HTML cards that track the 3D custody nodes (positioned by <CustodyNodes/> each frame). */
export function NodeLabels({ visible }: { visible: boolean }) {
  return (
    <div className={`node-labels ${visible ? 'is-visible' : ''}`}>
      {CUSTODY_NODES.map((n, i) => (
        <div
          key={n.id}
          className="node-label"
          data-node={n.id}
          ref={(el) => {
            nodeLabelEls[i] = el;
          }}
          data-state="upcoming"
          style={{ transform: 'translate3d(-999px,-999px,0)', ['--i' as string]: i }}
        >
          <div className="node-card">
            <Icon name={n.id} size={26} gold />
            <span>
              <span className="node-title">{n.title}</span>
              <span className="node-value">{n.value}</span>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
