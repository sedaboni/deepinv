import numpy as np
import deepinv as dinv
import hdf5storage
import torch
import os
from torch.utils.data import DataLoader
from deepinv.models.denoiser import ScoreDenoiser
from deepinv.optim.data_fidelity import *
from deepinv.optim.optimizers import *
from deepinv.training_utils import test
from torchvision import datasets, transforms
from deepinv.utils.parameters import get_GSPnP_params

torch.manual_seed(0)

num_workers = (
    4 if torch.cuda.is_available() else 0
)  # set to 0 if using small cpu, else 4
train = False
ckpt_path = "../checkpoints/GSDRUNet.ckpt"
if not os.path.exists(ckpt_path):
    ckpt_path = None
denoiser_name = "gsdrunet"
batch_size = 1
n_channels = 3
pretrain = True
problem = "deblur"
G = 1
img_size = 256
dataset = "set3c"
dataset_path = f"../datasets/{dataset}/images"
save_dir = f"../datasets/{dataset}/{problem}/"
crit_conv = "cost"
thres_conv = 1e-5
early_stop = True
verbose = True
k_index = 1
noise_model = "poisson"
poisson_gain = 10
bregman_potential = "Burg_entropy"
plot_metrics = True


# TODO : add kernel downloading code
kernels = hdf5storage.loadmat("../kernels/Levin09.mat")["kernels"]
filter_np = kernels[0, k_index].astype(np.float64)
filter_torch = torch.from_numpy(filter_np).unsqueeze(0).unsqueeze(0)

p = dinv.physics.BlurFFT(
    img_size=(3, img_size, img_size),
    filter=filter_torch,
    device=dinv.device,
    noise_model=dinv.physics.PoissonNoise(gain=poisson_gain, normalize=True),
)

data_fidelity = PoissonLikelihood(gain=poisson_gain)

val_transform = transforms.Compose(
    [
        transforms.ToTensor(),
    ]
)

dataset = datasets.ImageFolder(root=dataset_path, transform=val_transform)
dinv.datasets.generate_dataset(
    train_dataset=dataset,
    test_dataset=None,
    physics=p,
    device=dinv.device,
    save_dir=save_dir,
    max_datapoints=3,
    num_workers=num_workers,
)
dataset = dinv.datasets.HDF5Dataset(path=f"{save_dir}/dinv_dataset0.h5", train=True)
dataloader = DataLoader(
    dataset, batch_size=batch_size, num_workers=num_workers, shuffle=False
)

model_spec = {
    "name": denoiser_name,
    "args": {
        "in_channels": n_channels + 1,
        "out_channels": n_channels,
        "pretrained": ckpt_path,
        "train": False,
        "device": dinv.device,
    },
}

max_iter = 200
sigma_denoiser = 15 / 255.0
stepsize = 1.0
lamb = 2

params_algo = {"stepsize": stepsize, "g_param": sigma_denoiser, "lambda": lamb}
prior = {"grad_g": ScoreDenoiser(model_spec, sigma_normalize=False)}
F_fn = lambda x, cur_params, y, physics: lamb * data_fidelity.f(
    physics.A(x), y
) + prior["grad_g"][0].denoiser.potential(x, cur_params["g_param"])
model = Optim(
    algo_name="GD",
    prior=prior,
    data_fidelity=data_fidelity,
    params_algo=params_algo,
    early_stop=early_stop,
    max_iter=max_iter,
    crit_conv=crit_conv,
    thres_conv=thres_conv,
    backtracking=False,
    F_fn=F_fn,
    return_dual=False,
    verbose=True,
    bregman_potential=bregman_potential,
    return_metrics=plot_metrics,
)

test(
    model=model,  # Safe because it has forward
    test_dataloader=dataloader,
    physics=p,
    device=dinv.device,
    plot_images=True,
    plot_input=True,
    save_folder="../results/",
    plot_metrics=plot_metrics,
    verbose=verbose,
    wandb_vis=True,
)