import matplotlib.pyplot as plt

__all__ = ['get_figax']

DEFAULT_TX_COLORS = ['r', 'g', 'b', 'm', 'c', 'y', 'k']

def get_figax(n_tx, rows=111, figsize=(16,8), offset=28,
                left=0.03, right=0.97, top=0.97, bottom=0.03,
                tx_colors=None):
    fig = plt.figure(figsize=figsize)
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    ax = fig.add_subplot(rows)

    colors = tx_colors or DEFAULT_TX_COLORS
    tx_list = []
    for i in range(n_tx):
        tx = ax.twinx()
        color = colors[i % len(colors)]
        tx.spines['right'].set_color(color)
        tx.tick_params(axis='y', colors=color)
        tx.yaxis.label.set_color(color)
        if i >= 1:
            tx.spines['right'].set_position(('outward', -offset*i))
        tx_list.append(tx)

    return fig, ax, *tx_list
