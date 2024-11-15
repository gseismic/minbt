import matplotlib.pyplot as plt

__all__ = ['get_figax']

def get_figax(n_tx, rows=111, figsize=(16,8), offset=28,
                left=0.03, right=0.97, top=0.97, bottom=0.03,
                tx_colors=['r', 'g', 'b', 'm', 'c']):
    fig = plt.figure(figsize=figsize)
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    ax = fig.add_subplot(rows)

    tx_list = []
    for i in range(n_tx):
        tx = ax.twinx()
        if i >= 1:
            # tx.spines['right'].set_position(('axes', 1 + 0.05*i))
            tx.spines['right'].set_position(('outward', -offset*i))
        tx_list.append(tx)

    return fig, ax, *tx_list